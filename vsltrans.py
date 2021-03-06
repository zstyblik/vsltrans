# coding: utf-8
import os
import re
import signal
import sys
import threading
import time
import types

import varnishapi
from pprint import pprint

class VarnishLog:
    """ VarnishLog parser and interpreter """

    tags = 0
    vap = 0
    vslutil = 0
    endthread = False
    filter = 0
    logfile = ''
    rfmt = 0
    libvap = 'libvarnishapi.so.1'

    tagfilter = {}

    # Trx毎に格納
    # Stored in each Trx
    obj = {
        1: {},  # client
        2: {},  # backend
    }
    # パース前のデータ保存領域
    # Data storage area of ... before
    vslData = []

    # 出力順
    # Output order
    prnVarOrder = [
        'client',
        'server',
        'req',
        'bereq',
        'beresp',
        'obj',
        'resp',
        'storage',
    ]

    # アクセスを分割するセパレータ
    # Separator to divide access
    reqsep = {
        1: {
            'open': {
                'ReqStart': 'ReqStart',
            },
            'close': {
                'ReqEnd': 'ReqEnd',
            },
        },
        2: {
            'open': {
                'BackendOpen': 'BackendOpen',
                'BackendReuse': 'BackendReuse',
            },
            'close': {
                'Length': 'Length',
                #'BackendClose' : 'BackendClose',
            },
        },
    }

    def __init__(self):
        # ファイル入力用の正規表現
        # Regex for input file
        self.rfmt = re.compile('^ *([^ ]+) +([^ ]+) +([^ ]+) +(.*)$')

        self.filter = {
            0: {},
            # Client
            1: {
                #"Debug"                :"",
                "Error": self.filter_error,
                #"CLI"              :"",
                #"StatSess"         :"",
                "ReqEnd": self.filter_req_end,
                #"SessionOpen"      :"",
                #"SessionClose"     :"",
                #"BackendOpen"      :"",
                #"BackendXID"       :"",
                #"BackendReuse"     :"",
                #"BackendClose"     :"",
                #"HttpGarbage"      :"",
                "Backend": self.filter_backend,
                "Length": self.filter_length,
                "FetchError": self.filter_error,
                "RxRequest": self.filter_request,
                #"RxResponse"       :"",
                #"RxStatus"         :"",
                "RxURL": self.filter_request,
                "RxProtocol": self.filter_request,
                "RxHeader": self.filter_request,
                #"TxRequest"            :"",
                "TxResponse": self.filter_request,
                "TxStatus": self.filter_request,
                #"TxURL"                :"",
                "TxProtocol": self.filter_request,
                "TxHeader": self.filter_request,
                #"ObjRequest"       :"",
                "ObjResponse": self.filter_request,
                #"ObjStatus"            :"",
                #"ObjURL"           :"",
                "ObjProtocol": self.filter_request,
                "ObjHeader": self.filter_request,
                #"LostHeader"       :"",
                "TTL": [self.filter_ttl, self.filter_act_item],
                #"Fetch_Body"       :"",
                #"VCL_acl"          :"",
                "VCL_call": self.filter_action,
                "VCL_trace": [self.filter_trace, self.filter_act_item],
                "VCL_return": self.filter_action,
                #"VCL_error"            :"",
                "ReqStart": self.filter_req_start,
                #"Hit"              :"",
                "HitPass": [self.filter_hit_pass, self.filter_act_item],
                #"ExpBan"           :"",
                #"ExpKill"          :"",
                #"WorkThread"       :"",
                "ESI_xmlerror": self.filter_error,
                "Hash": [self.filter_hash, self.filter_act_item],
                #"Backend_health"   :"",
                "VCL_Log": self.filter_act_item,
                #"Gzip"             :"",
            },
            # Backend
            2: {
                #"Debug"                :"",
                "Error": self.filter_error,
                #"CLI"              :"",
                #"StatSess"         :"",
                #"ReqEnd"           :"",
                #"SessionOpen"      :"",
                #"SessionClose"     :"",
                #"BackendOpen"      :"",
                #"BackendXID"       :"",
                #"BackendReuse"     :"",
                #"BackendClose"     :"",
                #"HttpGarbage"      :"",
                #"Backend"          :"",
                "Length": self.filter_length,
                #"FetchError"       :"",
                #"RxRequest"            :"",
                "RxResponse": self.filter_request,
                "RxStatus": self.filter_request,
                "RxURL": self.filter_request,
                "RxProtocol": self.filter_request,
                "RxHeader": self.filter_request,
                "TxRequest": self.filter_request,
                #"TxResponse"       :"",
                #"TxStatus"         :"",
                "TxURL": self.filter_request,
                "TxProtocol": self.filter_request,
                "TxHeader": self.filter_request,
                #"ObjRequest"       :"",
                #"ObjResponse"      :"",
                #"ObjStatus"            :"",
                #"ObjURL"           :"",
                #"ObjProtocol"      :"",
                #"ObjHeader"            :"",
                #"LostHeader"       :"",
                #"TTL"              :"",
                #"Fetch_Body"       :"",
                #"VCL_acl"          :"",
                #"VCL_call"         :"",
                #"VCL_trace"            :"",
                #"VCL_return"       :"",
                #"VCL_error"            :"",
                #"ReqStart"         :"",
                #"Hit"              :"",
                #"HitPass"          :"",
                #"ExpBan"           :"",
                #"ExpKill"          :"",
                #"WorkThread"       :"",
                #"ESI_xmlerror"     :"",
                #"Hash"             :"",
                "Backend_health": self.filter_health
                #"VCL_Log"          :"",
                #"Gzip"             :"",
            },
        }
        self.vslutil = varnishapi.VSLUtil()
        self.tags = self.vslutil.tags

    def _sub_print_action_box(self, txt):
        """ Print-out action box """
        df = 13 - len(txt)
        spa = ' ' * (df // 2)
        spb = ' ' * ((df // 2) + (df % 2))
        print "+-------------+"
        print "|%s%s%s|" % (spa, txt, spb)
        print "+-------------+"

    def _sub_print_action_line(self, data, max_len):
        """ Print-out action vertical line """
        item = data['item']
        ret = data['return']
        print '      |'
        if len(item) > 0:
            for v in item:
                pad = ' ' * (max_len - len(v['key']))
                print '      | ' + v['key'] + pad + ' | ' + v['val']

        pad = ' ' * (max_len - 6)
        print '      | ' + max_len * ' ' + ' |'
        print '      | return' + pad + ' | ' + ret
        print '      |'

    def _sub_print_variable(self, data, key, prn):
        """ Print-out k:v variable(s) """
        if key not in data:
            return prn

        obj = data[key].items()
        for cat, v in obj:
            for vv in v:
                prn.append({
                    'key': (key + '.' + cat + '.' + vv['key']).strip('.'),
                    'val': vv['val']
                })

        prn.append(0)
        return prn

    def append_tag_filter(self, data):
        spl = data.split(':', 2)
        if len(spl) == 1:
            print '[ERROR] -m option format'
            return False

        tag = self.vap.VSL_NameNormalize(spl[0])
        if tag == '':
            print '[ERROR] -m option format'
            return False

        if tag not in self.tagfilter:
            self.tagfilter[tag] = []

        try:
            self.tagfilter[tag].append(re.compile(spl[1]))
        except re.error:
            print '[ERROR] -m regex format'
            return False

        return True

    def append_tag_name(self, raw):
        """ タグの名称追加 - Append name of tag """
        for v in raw:
            v['tagname'] = self.tags[v['type']][v['tag']]

    def attach_varnish_api(self):
        """ Attach to VarnishAPI """
        self.vap = varnishapi.VarnishAPI(self.libvap)

    def chk_max_length(self, data, key=''):
        max_len = 0
        if isinstance(data, list):
            for v in data:
                if isinstance(v, dict) and key in v:
                    length = len(v[key])
                    if max_len < length:
                        max_len = length

        else:
            for k, v in data.items():
                length = len(k)
                if max_len < length:
                    max_len = length

        return max_len

    def commit_trx(self, obj_type, fd):
        """ トランザクションデータをコミット - Commit transaction data """
        # if obj_type == 2:
        #   return
        base = self.obj[obj_type][fd][-1]
        raw = base['raw']
        base['curidx'] = -1
        base['info'] = {
            'hitpass': 0,
            'esi': 0,
            'restart': 0,
            'backend': []
        }
        base['time'] = {}
        #base['curactidx'] = -1

        self.incr_data(base)

        # ここから詳細データ作成
        # タグ名を付与
        # More data creation from here on
        # Grant the tag name ?
        self.append_tag_name(raw)
        # フィルタ実行
        # Run the filter
        self.loop_filter(base)
        # Vary情報の取得
        # Acquisition of vary information
        self.con_vary(base)
        # restart/ESI情報の作成
        # Create/get restart/ESI information ?
        self.con_restart_esi(base)
        # for client
        if obj_type == 1:
            # client/server.ip付与
            # grant client/server.ip
            self.set_var_client_server(base)

    def con_restart_esi(self, base):
        """ restart,ESIの情報を構築 - Build information about restart, ESI ? """
        restart = 0
        esi = 0
        #length  = []
        data = base['data']

        for v in data:
            info = v['info']
            if info == 'esi':
                esi += 1
                # length.add(v['length'])
            elif info == 'restart':
                restart += 1
        base['info']['restart'] = restart
        base['info']['esi'] = esi
        #base['info']['extraLength'] = length

    def con_trx(self, r):
        """ トランザクションごとのデータ作成 - Creating data per transaction """
        if not r:
            return

        # 値を作成
        # create value
        trx_type = r['type']
        if trx_type == 0:
            return

        tag = r['tag']
        fd = r['fd']
        if fd in self.obj[trx_type]:
            # fd is open ?
            if tag in self.reqsep[trx_type]['close']:
                # 開いてる
                # close(print target)
                self.obj[trx_type][fd][-1]['raw'].append(r)

                self.commit_trx(trx_type, fd)
                self.print_trx(trx_type, fd)
                if trx_type == 1:
                    # データ削除(Clientの場合のみ)
                    # delete data(only if Client ...???)
                    del self.obj[trx_type][fd]
            elif tag in self.reqsep[trx_type]['open']:
                if trx_type == 1:  # client
                    # 開く（バックエンドか何かしらのバグ）
                    # to open(bug or some kind of back-end)
                    del self.obj[trx_type][fd]
                    self.obj[trx_type][fd] = [{'raw': []}]
                    self.obj[trx_type][fd][-1]['raw'].append(r)
                elif trx_type == 2:  # Backend
                    # 開く（バックエンドか何かしらのバグ）
                    # ESI対応で使われたかのチェックを行う
                    # to open(bug or some kind of back-end)
                    # I do check if it was used in corresponding ESI
                    #del self.obj[trx_type][fd]
                    self.obj[trx_type][fd].append({'raw': []})
                    self.obj[trx_type][fd][-1]['raw'].append(r)

            else:
                # 通常格納
                # normally stored
                self.obj[trx_type][fd][-1]['raw'].append(r)
        elif tag in self.reqsep[trx_type]['open']:
            # 開く
            # I open ???
            self.obj[trx_type][fd] = [{'raw': []}]
            self.obj[trx_type][fd][-1]['raw'].append(r)

    def con_vary(self, base):
        """ varyの情報を構築 - Build information about vary """
        for trx in base['data']:
            var = trx['var']
            if 'obj' in var and 'http' in var['obj']:
                for objhttp in var['obj']['http']:
                    if 'vary' == objhttp['lkey']:
                        spl = objhttp['val'].split(',')
                        for tgkey in spl:
                            val = ''
                            tgkeylow = tgkey.lower()
                            if 'req' in var and 'http' in var['req']:
                                for reqhttp in var['req']['http']:
                                    if tgkeylow == reqhttp['lkey']:
                                        val = reqhttp['val']
                                        trx['hash']['vary'].append(
                                            {'key': tgkey, 'val': val})
                                if val == '':
                                    trx['hash']['vary'].append(
                                        {'key': tgkey, 'val': ''})

    def file_loop(self, event):
        """ Read lines from file specified by self.logfile """
        if not os.path.exists(self.logfile):
            self.endthread = True
            return

        f = open(self.logfile)
        for line in f.readlines():
            self.vslData.append(self.parse_file(line))

        f.close()
        self.endthread = True

    def filter_act_item(self, base, rawline):
        """ Action内のアイテムを格納 - The store items of Action in ??? """
        curidx = base['curidx']
        curactidx = base['data'][curidx]['curactidx']

        data = base['data'][curidx]['act'][curactidx]['item']
        if 'aliasmsg' in rawline:
            data.append({'key': rawline['tag'], 'val': rawline['aliasmsg']})
        else:
            data.append({'key': rawline['tag'], 'val': rawline['msg']})

    def filter_action(self, base, rawline):
        """ アクションを構築 - Build action
        # 12 VCL_call     c fetch 3 41.9 23 103.5 24 109.17
        #   12 VCL_call     c pass 17 81.5 pass
        """
        spl = rawline['msg'].split(' ')
        msg = spl.pop(0)
        ret = ''
        item = []
        tracetmp = ''
        # traceとreturnを構築
        # Build and return trace
        if len(spl) > 0:
            for v in spl:
                if v[0].isdigit():
                    # trace
                    spl2 = v.split('.')
                    if len(spl2) == 1:
                        # trace count
                        tracetmp = '(VRT_Count:' + v + ' '
                    else:
                        # trace other
                        tracetmp += 'line:' + spl2[0] + ' pos:' + spl2[1] + ')'
                        item.append({'key': 'VCL_trace', 'val': tracetmp})
                else:
                    ret = v

        curidx = base['curidx']
        # ESI-check
        if msg == 'recv' and base['data'][curidx]['curactidx'] > 0:
            self.incr_data(base, 'esi')
            curidx = base['curidx']

        data = base['data'][curidx]['act']
        if rawline['tag'] == 'VCL_return':
            curactidx = base['data'][curidx]['curactidx']
            data[curactidx]['return'] = msg
            # restartとESIの場合はIncrする
            # I will incr in the case of ESI and restart
            if msg == 'restart':
                self.incr_data(base, 'restart')

        else:
            base['data'][curidx]['curactidx'] += 1
            data.append({'function': msg, 'return': ret, 'item': item})

    def filter_backend(self, base, rawline):
        """ バックエンド情報の格納 - Store backend information """
        curidx = base['curidx']
        data = base['data'][curidx]['backend']
        cvar = base['data'][curidx]['var']
        #'msg': '14 default default',
        #         fd name    verbose
        spl = rawline['msg'].split(' ')
        backend_fd = long(spl[0])
        #data['raw']        = copy.deepcopy(self.obj[2][backend_fd])
        if (backend_fd not in self.obj[2]
                or len(self.obj[2][backend_fd]) == 0):
            return

        data['raw'] = self.obj[2][backend_fd].pop(0)
        if 'curidx' not in data['raw'].keys():
            # {'raw': [
            #   {'msg': 'cms02', 'type': 2L, 'tag': 'BackendReuse', 'fd': 25L, 'typeName': 'b'},
            #   {'msg': 'cms02', 'type': 2L, 'tag': 'BackendClose', 'fd': 25L, 'typeName': 'b'}
            # ]}
            return

        bcuridx = data['raw']['curidx']
        bvar = data['raw']['data'][bcuridx]['var']
        data['name'] = spl[1]
        data['verbose'] = spl[2]
        base['data'][curidx]['backendname'] = spl[2]

        base['info']['backend'].append(spl[2])

        base['data'][curidx]['length'] = data['raw']['data'][bcuridx]['length']
        # link var
        for k, v in bvar.items():
            cvar[k] = v

    def filter_error(self, base, rawline):
        """ error系を格納 - Store information about errors ? """
        curidx = base['curidx']
        data = base['data'][curidx]['error']

        data.append({'key': rawline['tag'], 'val': rawline['msg']})

        '''
          {'fd': 12L,
           'msg': 'no backend connection',
           'tag': 'FetchError',
           'tagname': '',
           'type': 1L,
           'typeName': 'c'},
        '''

    def filter_hash(self, base, rawline):
        """ ハッシュ情報を格納 - Store hash information """
        curidx = base['curidx']
        data = base['data'][curidx]['hash']['hash']
        data.append(rawline['msg'])

    def filter_hit_pass(self, base, rawline):
        """ Increase hitpass """
        base['info']['hitpass'] += 1

    def filter_health(self, base, rawline):
        """
        0 Backend_health - recommender02 Still healthy 4--X-RH 5 3 5 0.003418 0.003802 HTTP/1.1 200 OK
        """
        pass

    def filter_length(self, base, rawline):
        """ lengthを取得 - Get length """
        curidx = base['curidx']
        base['data'][curidx]['length'] = int(rawline['msg'])

    def filter_req_end(self, base, rawline):
        """ 実行時間を取得 - Get execution time """
        spl = rawline['msg'].split(' ')
        curidx = base['curidx']
        base['data'][curidx]['time'] = {}
        data = base['time']
        data['start'] = float(spl[1])
        data['total'] = float(spl[2]) - data['start']
        data['accept'] = float(spl[3])
        data['execute'] = float(spl[4])
        data['exit'] = float(spl[5])

    def filter_req_start(self, base, rawline):
        """ クライアント情報取得 - Acquisition of client information
        #                    client.ip   port     xid
        #          'msg': '192.168.1.199 47475 1642652384',
        # WSP(sp, SLT_ReqStart, "%s %s %u", sp->addr, sp->port,  sp->xid);
        """
        curidx = base['curidx']
        if 'req' not in base['data'][curidx]['var']:
            base['data'][curidx]['var']['req'] = {}
        data = base['data'][curidx]['var']['req']
        spl = rawline['msg'].split(' ')
        base['client'] = {
            'ip': spl[0],
            'port': spl[1],
        }
        data['xid'] = [{
            'key': '',
            'lkey': '',
            'val': spl[2],
        }]

    def filter_request(self, base, rawline):
        """ req.urlなどを格納 - Store req.url """
        curidx = base['curidx']
        data = base['data'][curidx]['var']
        msg = rawline['msg']
        spl = rawline['tagname'].split('.')
        cmpo = spl[0]
        prop = spl[1]

        if cmpo not in data:
            data[cmpo] = {}
        if prop not in data[cmpo]:
            data[cmpo][prop] = []

        if prop == 'http':
            msg_spl = msg.split(':')
            data[cmpo][prop].append({
                'key': msg_spl[0],
                'lkey': msg_spl[0].lower(),
                'val': ":".join(msg_spl[1:]).lstrip() })
        else:
            data[cmpo][prop].append({'key': '', 'lkey': '', 'val': msg})

    def filter_tag_filter(self, obj_type, fd):
        cnt = len(self.tagfilter)
        if cnt == 0:
            return True

        base = self.obj[obj_type][fd][-1]
        cmp_list = []
        # client
        for raw in base['raw']:
            tag = raw['tag']
            msg = raw['msg']
            if tag in self.tagfilter:
                for tf in self.tagfilter[tag]:
                    exec_flag = True
                    for chk in cmp_list:
                        if tf == chk:
                            exec_flag = False
                            break

                    if exec_flag and tf.search(msg):
                        cmp_list.append(tf)
                        cnt -= 1
                        if cnt == 0:
                            return True

        # backend
        for idx in range(base['curidx'] + 1):
            if 'raw' in base['data'][idx]['backend']:
                for raw in base['data'][idx]['backend']['raw']['raw']:
                    tag = raw['tag']
                    msg = raw['msg']
                    if tag in self.tagfilter:
                        for tf in self.tagfilter[tag]:
                            exec_flag = True
                            for chk in cmp_list:
                                if tf == chk:
                                    exec_flag = False
                                    break
                            if exec_flag and tf.search(msg):
                                cmp_list.append(tf)
                                cnt -= 1
                                if cnt == 0:
                                    return True

        return False

    def filter_trace(self, base, rawline):
        """ traceを解釈 - Interpret trace information """
        spl = rawline['msg'].split(' ')
        spl2 = spl[1].split('.')
        rawline['aliasmsg'] = '(VRT_Count:%s line:%s pos:%s)' \
            % (spl[0], spl2[0], spl2[1])

    def filter_ttl(self, base, rawline):
        """ フィルタ情報を格納 - Stores information filter
                               0       1    2     3    4     5      6    7    8      9
                              xid      src  ttl grace keep basetime age date expire max-age
          538 TTL          c 2480419881 VCL 864000 -1 -1 1367990868 -0
          663 TTL          c 2480419886 RFC 3600 -1 -1 1367990868 0 1367990868 1367990968 3600
        """
        spl = rawline['msg'].split(' ')
        spl[5] = time.strftime("%Y-%m-%d %H:%M:%S +0000",
                               time.gmtime(float(spl[5])))
        if spl[1] == 'RFC':
            if int(spl[8]) > 0:
                spl[8] = time.strftime("%Y-%m-%d %H:%M:%S +0000",
                                       time.gmtime(float(spl[8])))
            if int(spl[7]) > 0:
                spl[7] = time.strftime("%Y-%m-%d %H:%M:%S +0000",
                                       time.gmtime(float(spl[7])))

            rawline['aliasmsg'] = "[RefTime]=%s [src]=RFC [ttl]=%s " \
                "[grace]=%s [keep]=%s [Age]=%s [Date]=%s [Expires]=%s " \
                "[Max-Age]=%s" % (spl[5], spl[2], spl[3], spl[4],
                                  spl[6], spl[7], spl[8], spl[9])
        else:
            rawline['aliasmsg'] = "[RefTime]=%s [src]=VCL [ttl]=%s "\
                "[grace]=%s [keep]=%s [Age]=%s" % (spl[5], spl[2], spl[3],
                                                   spl[4], spl[6])

    def incr_data(self, base, info=''):
        """ データ配列の作成 - Create data array """
        if 'data' not in base:
            base['data'] = []
        base['data'].append({
            'var': {},  # req, obj, resp ,beresp
            'act': [],  # recv, pass, miss ,fetch ...
            'hash': {'hash': [], 'vary': []},
            'backend': {},
            'error': [],
            'curactidx': -1,
            'info': info,  # esi , restart
            'length': 0,
            'backendname': '',
        })
        base['curidx'] += 1

    def loop_filter(self, base):
        """ フィルタのループ """
        raw = base['raw']
        for v in raw:
            var_type = v['type']
            tag = v['tag']
            if tag in self.filter[var_type]:
                if isinstance(self.filter[var_type][tag], list):
                    for func in self.filter[var_type][tag]:
                        func(base, v)
                else:
                    self.filter[var_type][tag](base, v)

    def parse_file(self, data):
        """
        {'fd': 0L,
         'msg': 'Wr 200 19 PONG 1367695724 1.0',
         'tag': 'CLI',
         'type': 0L,
         'typeName': '-'}
        データを読み込む場合
        If you want to read the data
         1284 RxHeader     b Content-Type: image/png

        """
        m = self.rfmt.search(data.rstrip("\r\n"))

        if not m:
            return

        r = {
            'fd': int(m.group(1)),
            'msg': m.group(4),
            'tag': m.group(2),
            'typeName': m.group(3),
        }

        if r['typeName'] == '-':
            r['type'] = 0
        elif r['typeName'] == 'c':
            r['type'] = 1
        elif r['typeName'] == 'b':
            r['type'] = 2
        return(r)

    def print_action(self, base, idx):
        """ Print-out actions Varnish has done/taken. """
        data = base['data'][idx]['act']
        max_len = 6  # return
        self.print_line('#')
        print 'Action infomation.'
        self.print_line()
        for v in data:
            length = self.chk_max_length(v['item'], 'key')
            if max_len < length:
                max_len = length

        for v in data:
            self._sub_print_action_box(v['function'])
            self._sub_print_action_line(v, max_len)

        print

    def print_error(self, base, idx):
        """ Print-out errors during transaction(?) """
        data = base['data'][idx]['error']
        if len(data) == 0:
            return

        max_len = self.chk_max_length(data, 'key')
        self.print_line('#')
        print 'Error infomation.'
        self.print_line()
        for v in data:
            pad = ' ' * (max_len - len(v['key']))
            print "%s%s | %s" % (v['key'], pad, v['val'])

        self.print_line()
        print

    def print_general_info(self, base):
        """ Print-out general info about transaction """
        data = base['data']
        reqdata = data[0]
        # junkセッション対応
        # junk corresponding(related to?) session
        if 'resp' in data[0]['var']:
            respvar = data[0]['var']['resp']
        else:
            respvar = False

        client = base['client']
        info = base['info']
        timeinfo = base['time']
        host = ''
        if 'http' in reqdata['var']['req']:
            for v in reqdata['var']['req']['http']:
                if v['lkey'] == 'host':
                    host = v['val']
                    break

        print 'General Info.'
        self.print_line()
        print "Client ip:port  | %s:%s" % (client['ip'], client['port'])
        print "Request host    | %s" % (host)
        print "Response size   | %s byte" % (reqdata['length'])
        if respvar:
            print "Response Status | %s %s %s" % (respvar['proto'][0]['val'],
                    respvar['status'][0]['val'], respvar['response'][0]['val'])

        print "Total time      | %s sec" % (round(timeinfo['total'], 5))
        print "HitPass count   | %s" % (info['hitpass'])
        print "Restart count   | %s" % (info['restart'])
        print "ESI count       | %s" % (info['esi'])
        print "Backend count   | %s" % (len(info['backend']))
        for v in info['backend']:
            print " +Backend       | %s" % (v)

        self.print_line()
        print

    def print_info(self, base, idx):
        """ Print-out object information """
        data = base['data'][idx]
        hashdata = data['hash']
        ret = ''
        self.print_line('#')
        print 'Object infomation.'
        self.print_line()
        # type
        if not data['info'] == '':
            print "Type        | %s" % (data['info'])

        #hash and vary
        for hitem in hashdata['hash']:
            ret += '"' + hitem + '" + '

        print "Hash        | %s" % (ret.rstrip('+ '))
        if len(hashdata['vary']) > 0:
            maxlen = self.chk_max_length(
                hashdata['vary'], 'key') + len('req.http.')
            self.print_line()
            for vary in hashdata['vary']:
                pad = ' ' * (maxlen - len('req.http.' + vary['key']))
                print "Vary        | req.http.%s%s | %s" \
                        % (vary['key'], pad, vary['val'])

        # length
        print "Object size | %s" % (data['length'])
        # backend
        print "Backend     | %s" % (data['backendname'])
        self.print_line()
        print

    def print_line(self, char='-', length=70):
        """ Function to print delimiters """
        print char * length

    def print_loop(self, event):
        """ Infinite print-out loop """
        while not event.isSet():
            if len(self.vslData) == 0:
                if self.endthread:
                    break
                time.sleep(0.1)
                continue

            while True:
                if len(self.vslData) == 0:
                    break

                self.con_trx(self.vslData.pop(0))

            if self.endthread:
                break

    def print_pad(self, k, v, max_len, dlm=" | "):
        """ Print padded string ? """
        fmt = "%- " + str(max_len) + "s" + dlm + "%s"
        print fmt % (k, v)

    def print_trx(self, trx_type, fd):
        if not trx_type == 1:
            return

        base = self.obj[trx_type][fd][-1]
        if not self.filter_tag_filter(trx_type, fd):
            return

        # 一旦テストで0を指定している（restartとかになると変わるので注意）
        # (Note that it is change when it comes to such as restart) you have
        # specified a 0 in the test once
        idx = 0
        self.print_line('<')
        print 'START transaction.'
        self.print_line('<')
        # 全体のInfoを出力
        # Output of entire info
        self.print_general_info(base)
        for idx in range(base['curidx'] + 1):
            # 個別のInfoを出力
            # Outputs individual info
            self.print_info(base, idx)
            # エラーを表示
            # Print error information
            self.print_error(base, idx)
            # アクションを表示
            # Print action
            self.print_action(base, idx)
            # 変数情報を表示
            # Print variable information
            self.print_variable(base, idx)

        self.print_line('-')
        self.print_line('>')
        print 'END transaction.'
        self.print_line('>')
        print

    def print_variable(self, base, idx):
        """ Print-out variable information, resp. HTTP req and rsp """
        data = base['data'][idx]['var']
        prn = []
        for key in self.prnVarOrder:
            self._sub_print_variable(data, key, prn)

        if len(prn) > 0:
            max_len = self.chk_max_length(prn, 'key')
            max_len_val = self.chk_max_length(prn, 'val')
            line_len = (max_len + max_len_val + len(' | '))
            self.print_line('#')
            print 'Variable infomation.'
            self.print_line('-', line_len)
            for v in prn:
                if v == 0:
                    self.print_line('-', line_len)
                else:
                    self.print_pad(v['key'], v['val'], max_len)

            print

    def run_vsl(self):
        """ Run VSL """
        self.start_thread(self.vap_loop)

    def run_file(self, file_name):
        """ Run VSL from file """
        self.logfile = file_name
        self.start_thread(self.file_loop)

    def set_var_client_server(self, base):
        """ client.*とserver.*を設定（serverはデータ元がないので・・・）
        Set Server.* and Client.*, because there is no data source server
        """
        data = base['data']
        for var in data:
            var['client'] = {
                'ip': [{
                    'key': '',
                    'lkey': '',
                    'val': base['client']['ip'],
                }]
            }

    def sighandler(self, event, signr, handler):
        """ スレッド周りの処理 - Process signal/signal to stop """
        event.set()

    def start_thread(self, inloop):
        """ Start VSL thread """
        threads = []
        e = threading.Event()
        signal.signal(signal.SIGINT, (lambda a, b: self.sighandler(e, a, b)))

        # スレッド作成
        # Create Thread
        # if self.vap:
        threads.append(threading.Thread(target=inloop, args=(e,)))
        threads[-1].start()

        threads.append(threading.Thread(target=self.print_loop, args=(e,)))
        threads[-1].start()
        # 終了待ち
        # Wait for thread to join
        for th in threads:
            while th.isAlive():
                time.sleep(0.5)
            th.join()

    def vap_callback(self, priv, tag, fd, length, spec, ptr, bm):
        self.vslData.append(self.vap.normalize_dic(priv, tag, fd, length, spec,
                                                  ptr, bm))

    def vap_loop(self, event):
        while not event.isSet():
            self.vap.VSL_NonBlockingDispatch(self.vap_callback)
            time.sleep(0.1)

        self.endthread = True


def dump(obj):
    """ return a printable representation of an object for debugging """
    newobj = obj
    if isinstance(obj, list):
        # リストの中身を表示できる形式にする
        # Display/format contents of the list
        newobj = []
        for item in obj:
            newobj.append(dump(item))

    elif isinstance(obj, tuple):
        # タプルの中身を表示できる形式にする
        # Display/format contents of the tuple
        temp = []
        for item in obj:
            temp.append(dump(item))

        newobj = tuple(temp)
    elif isinstance(obj, set):
        # セットの中身を表示できる形式にする
        # Display/format contents of the set
        temp = []
        for item in obj:
            # itemがclassの場合はdump()は辞書を返すが,辞書はsetで使用できないので文字列にする
            # Return dump of a dictionary if item is a class
            temp.append(str(dump(item)))

        newobj = set(temp)
    elif isinstance(obj, dict):
        # 辞書の中身（キー、値）を表示できる形式にする
        # Display/format contents of dict as k, v
        newobj = {}
        for key, value in obj.items():
            # keyがclassの場合はdump()はdictを返すが,dictはキーになれないので文字列にする
            newobj[str(dump(key))] = dump(value)

    elif isinstance(obj, types.FunctionType):
        # 関数を表示できる形式にする
        # Display/format function
        newobj = repr(obj)
    elif '__dict__' in dir(obj):
        # 新しい形式のクラス class Hoge(object)のインスタンスは__dict__を持っている
        newobj = obj.__dict__.copy()
        if ' object at ' in str(obj) and not '__type__' in newobj:
            newobj['__type__'] = str(obj).replace(" object at ",
                                                  " #").replace("__main__.", "")

        for attr in newobj:
            newobj[attr] = dump(newobj[attr])

    return newobj

# ref:http://tomoemon.hateblo.jp/entry/20090921/p1
def main():
    """ Main - parse args, fire up VSL """
    argv = sys.argv
    vsl = VarnishLog()
    opt = {}
    cur = ''
    for v in argv:
        if v[0] == '-':
            cur = v
        elif not cur == '':
            if cur not in opt:
                opt[cur] = []

            opt[cur].append(v)

    if '-libvapi' in opt:
        vsl.libvap = opt['-libvapi'][0]

    # VarnishAPIに接続
    # Connect to Varnish API
    vsl.attach_varnish_api()

    if '-m' in opt:
        for v in opt['-m']:
            if not vsl.append_tag_filter(v):
                return
    #-imの対応をそのうち書く(ignore -m)

    if '-f' in opt:
        vsl.run_file(opt['-f'][0])
    else:
        vsl.run_vsl()

def var_dump(obj):
    """ Dump given object """
    pprint(dump(obj))

if __name__ == '__main__':
    main()
