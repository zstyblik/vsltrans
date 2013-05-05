# coding: utf-8
import varnishapi

import threading,time,signal,copy,sys,re,os


#
#restart�΍�ŕ�����req.http�Ƃ������Ă�悤�ɂ���
#


'''
�A�N�Z�X�̊J�n
	ReqStart�@�`�@ReqEnd

	BackendReuse�@�`�@Length
	BackendOpen�@�`�@BackendClose


'''
def main():

	argv = sys.argv
	argc = len(argv)

	vsl = VarnishLog()
	
	opt = {}
	cur = ''
	for v in argv:
		if v[0] == '-':
			cur = v
		elif not cur == '':
			if not opt.has_key(cur):
				opt[cur] = []
			opt[cur].append(v)

	if opt.has_key('-libvapi'):
		vsl.libvap = opt['-libvapi'][0]
	if opt.has_key('-f'):
		vsl.runFILE(opt['-f'][0])
	else:
		vsl.runVSL()
	

class VarnishLog:
	tags      = 0
	vap       = 0
	vslutil   = 0
	endthread = False
	filter    = 0
	logfile   = ''
	rfmt      = 0
	libvap    = 'libvarnishapi.so.1'
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
	
	#�t�B���^�̃��[�v
	def loopFilter(self, base):
		raw    = base['raw']
		curidx = base['curidx']
		
		
		
		for v in raw:
			type = v['type']
			tag  = v['tag']
			if self.filter[type].has_key(tag):
				if isinstance(self.filter[type][tag], list):
					for func in self.filter[type][tag]:
						func(base,v)
				else:
					self.filter[type][tag](base,v)

	#�o�b�N�G���h���̊i�[
	def filterBackend(self, base, rawline):
		curidx          = base['curidx']
		data            = base['data'][curidx]['backend']
		cvar            = base['data'][curidx]['var']

		
		#'msg': '14 default default',
		#         fd name    verbose
		spl                 = rawline['msg'].split(' ')
		backendFd           = long(spl[0])
		#data['raw']        = copy.deepcopy(self.obj[2][backendFd])
		data['raw']         = self.obj[2][backendFd].pop(0)
		
		bcuridx             = data['raw']['curidx']
		
		bvar                = data['raw']['data'][bcuridx]['var']
		data['name']                        = spl[1]
		data['verbose']                     = spl[2]
		base['data'][curidx]['backendname'] = spl[2]
		
		base['info']['backend'].append(spl[2])

		base['data'][curidx]['length']          = data['raw']['data'][bcuridx]['length']
		#link var
		for k,v in bvar.items():
			cvar[k] = v
	
	#length���擾
	def filterLength(self, base, rawline):

		curidx          = base['curidx']

		base['data'][curidx]['length'] = int(rawline['msg'])

	
	#trace������
	def filterTrace(self, base, rawline):
		spl  = rawline['msg'].split(' ')
		spl2 = spl[1].split('.')
		
		rawline['aliasmsg'] = '(VRT_Count:%s line:%s pos:%s)' % (spl[0], spl2[0], spl2[1])
	
	#error�n���i�[
	def filterError(self, base, rawline):
		curidx     = base['curidx']
		data       = base['data'][curidx]['error']

		data.append({'key':rawline['tag'],'val':rawline['msg']})

		'''
		  {'fd': 12L,
		   'msg': 'no backend connection',
		   'tag': 'FetchError',
		   'tagname': '',
		   'type': 1L,
		   'typeName': 'c'},
		'''
	
	#Action���̃A�C�e�����i�[
	def filterActItem(self, base, rawline):
		curidx     = base['curidx']
		curactidx  = base['data'][curidx]['curactidx']


		data       = base['data'][curidx]['act'][curactidx]['item']
		if rawline.has_key('aliasmsg'):
			data.append({'key' : rawline['tag'],'val' : rawline['aliasmsg']})
		else:
			data.append({'key' : rawline['tag'],'val' : rawline['msg']})
	
	#���s���Ԃ��擾
	def filterReqEnd(self, base, rawline):
		spl                          = rawline['msg'].split(' ')
		curidx                       = base['curidx']
		base['data'][curidx]['time'] = {}
		data                         = base['time']
		data['start']   = float(spl[1])
		data['total']   = float(spl[2]) - data['start']
		data['accept']  = float(spl[3])
		data['execute'] = float(spl[4])
		data['exit']    = float(spl[5])

	#�A�N�V�������\�z
	def filterAction(self, base, rawline):
	
		#12 VCL_call     c fetch 3 41.9 23 103.5 24 109.17
		#   12 VCL_call     c pass 17 81.5 pass
		#

		spl            = rawline['msg'].split(' ')
		msg            = spl.pop(0)
		ret            = ''
		item           = []
		tracetmp       = ''
		#trace��return���\�z
		if(len(spl) > 1):
			for v in spl:
				if v[0].isdigit():
					#trace
					spl2 = v.split('.')
					if len(spl2)==1:
						#trace count
						tracetmp = '(VRT_Count:' + v + ' '
					else:
						#trace other
						tracetmp += 'line:' + spl2[0] + ' pos:' + spl2[1] + ')'
						item.append({'key':'VCL_trace','val':tracetmp})
				else:
					ret = v
		
		curidx         = base['curidx']
		
		#ESI-check
		if msg == 'recv' and base['data'][curidx]['curactidx'] > 0:

			self.incrData(base, 'esi')
			curidx = base['curidx']

		data           = base['data'][curidx]['act']
		
		
		if rawline['tag'] == 'VCL_return':
			curactidx = base['data'][curidx]['curactidx']
			data[curactidx]['return'] = msg
			
			#restart��ESI�̏ꍇ��Incr����
			if msg == 'restart':
				self.incrData(base, 'restart')
			
			
		else:
			base['data'][curidx]['curactidx'] += 1
			data.append({'function' : msg,'return' : ret,'item' : item})

	#�N���C�A���g���擾
	def filterReqStart(self, base, rawline):
		#                    client.ip   port     xid
		#          'msg': '192.168.1.199 47475 1642652384',
		#WSP(sp, SLT_ReqStart, "%s %s %u", sp->addr, sp->port,  sp->xid);
		curidx         = base['curidx']
		if not base['data'][curidx]['var'].has_key('req'):
			base['data'][curidx]['var']['req'] = {}
		data           = base['data'][curidx]['var']['req']
		spl = rawline['msg'].split(' ')
		base['client'] = {
			'ip'   : spl[0],
			'port' : spl[1],
			}
		data['xid'] = [{
			'key'  : '',
			'lkey' : '',
			'val'  : spl[2],
			}]

	#restart,ESI�̏����\�z
	def conRestartESI(self,base):
		restart = 0
		esi     = 0
		#length  = []
		data = base['data']
		
		for v in data:
			info = v['info']
			if info == 'esi':
				esi += 1
				#length.add(v['length'])
			elif info == 'restart':
				restart += 1
		base['info']['restart']     = restart
		base['info']['esi']         = esi
		#base['info']['extraLength'] = length

	#vary�̏����\�z
	def conVary(self,base):
		for trx in base['data']:
			var = trx['var']
			if var.has_key('obj') and var['obj'].has_key('http'):
				for objhttp in var['obj']['http']:
					if 'vary' == objhttp['lkey']:
						spl = objhttp['val'].split(',')
						for tgkey in spl:
							val = ''
							tgkeylow = tgkey.lower()
							if var.has_key('req') and var['req'].has_key('http'):
								for reqhttp in var['req']['http']:
									if tgkeylow == reqhttp['lkey']:
										val = reqhttp['val']
										trx['hash']['vary'].append({'key' : tgkey, 'val' : val})
								if val == '':
									trx['hash']['vary'].append({'key' : tgkey, 'val' : ''})
							
	def filterHash(self, base, rawline):
		curidx = base['curidx']
		data   = base['data'][curidx]['hash']['hash']
		data.append(rawline['msg'])

	#req.url�Ȃǂ��i�[
	def filterRequest(self, base, rawline):
		curidx = base['curidx']
		data   = base['data'][curidx]['var']
		msg    = rawline['msg']
		spl    = rawline['tagname'].split('.')
		cmpo   = spl[0]
		prop   = spl[1]
		
		
		if not data.has_key(cmpo):
			data[cmpo] = {}
		if not data[cmpo].has_key(prop):
			data[cmpo][prop] = []

		if prop == 'http':
			spl = msg.split(':')
			data[cmpo][prop].append({'key':spl[0], 'lkey':spl[0].lower(), 'val':spl[1].lstrip()})
		else:
			data[cmpo][prop].append({'key':'', 'lkey':'', 'val':msg})
			
	obj = {
		1 : {}, #client
		2 : {}, #backend
	}
	
	#�A�N�Z�X�𕪊�����Z�p���[�^
	reqsep  = {
		1 : {
			'open' : {
				'ReqStart'     : 'ReqStart',
				},
			'close' : {
				'ReqEnd'       : 'ReqEnd',
				},
			},
		2 : {
			'open' : {
				'BackendOpen'  : 'BackendOpen',
				'BackendReuse' : 'BackendReuse',
				},
			'close' : {
				'Length'       : 'Length',
				#'BackendClose' : 'BackendClose',
				},
			},
		}
	
	#�p�[�X�O�̃f�[�^�ۑ��̈�
	vslData = []
	
	#�f�[�^�z��̍쐬
	def incrData(self,base, info=''):
		if not base.has_key('data'):
			base['data']   = []
		base['data'].append({
			'var'         : {},	#req, obj, resp ,beresp
			'act'         : [],	#recv, pass, miss ,fetch ...
			'hash'        : {'hash':[],'vary':[]},
			'backend'     : {},
			'error'       : [],
			'curactidx'   : -1,
			'info'        : info, #esi , restart
			'length'      : 0,
			'backendname' : '',
			})
		base['curidx'] += 1
	
	#�g�����U�N�V�����f�[�^���R�~�b�g
	def commitTrx(self, type, fd):
		#if type == 2:
		#	return
		base           = self.obj[type][fd][-1]
		raw            = base['raw']
		base['curidx'] = -1
		base['info']   = {'esi':0,'restart':0,'backend':[]}
		base['time']   = {}
		#base['curactidx'] = -1

		self.incrData(base)
		
		#���curidx�Ή����s��
		#######################
		#��������ڍ׃f�[�^�쐬

		#�^�O����t�^
		self.apdTagName(raw)

		#�t�B���^���s
		self.loopFilter(base)
		
		#Vary���̎擾
		self.conVary(base)
		
		#restart/ESI���̍쐬
		self.conRestartESI(base)
		
		#######################
		#for client
		if type == 1:
			#client/server.ip�t�^
			self.setVarClientServer(base)


	
	
	def printTrx(self,type, fd):
		if not type == 1:
			return
		base           = self.obj[type][fd][-1]
		
		#print var
		#��U�e�X�g��0���w�肵�Ă���irestart�Ƃ��ɂȂ�ƕς��̂Œ��Ӂj
		idx = 0
		
		self.printLine('<')
		print 'START transaction.'
		self.printLine('<')
		#�S�̂�Info���o��
		self.printGeneralInfo(base)
		for idx in range(base['curidx'] + 1):

			#�ʂ�Info���o��
			self.printInfo(base,idx)

			#�G���[��\��
			self.printError(base,idx)

			#�A�N�V������\��
			self.printAction(base,idx)

			#�ϐ�����\��
			self.printVariable(base,idx)

		self.printLine('>')
		print 'END transaction.'
		self.printLine('>')
		print

		
	def printGeneralInfo(self,base):
		data     = base['data']
		reqdata  = data[0]
		respvar  = data[0]['var']['resp']
		client   = base['client']
		info     = base['info']
		timeinfo = base['time']
		host    = ''
		if reqdata['var']['req'].has_key('http'):
			for v in reqdata['var']['req']['http']:
				if v['lkey'] == 'host':
					host = v['val']
					break

		#self.printLine('#')
		print 'General Info.'
		self.printLine()
		print 'Client ip:port  | ' +client['ip'] + ':' + client['port']
		print 'Request host    | ' + host
		print 'Response size   | ' + str(reqdata['length']) + ' byte'
		print 'Response Status | ' + respvar['proto'][0]['val'] +' '+ respvar['status'][0]['val'] +' ' + respvar['response'][0]['val']
		print 'Total time      | ' + str(round(timeinfo['total'],5)) + ' sec'
		print 'Restart count   | ' + str(info['restart'])
		print 'ESI count       | ' + str(info['esi'])
		print 'Backend count   | ' + str(len(info['backend']))
		for v in info['backend']:
			print ' +Backend       | ' + v

		self.printLine()
		print

	def printError(self,base,idx):
		data = base['data'][idx]['error']
		if len(data) == 0:
			return

		max = self.chkMaxLength(data,'key')

		self.printLine('#')
		print 'Error infomation.'
		self.printLine()

		for v in data:
			pad = ' ' * (max - len(v['key']))
			print v['key'] + pad + ' | ' + v['val']

		self.printLine()
		print
	
	def printInfo(self,base,idx):
		data     = base['data'][idx]
		hashdata = data['hash']
		
		ret  = ''

		self.printLine('#')
		print 'Object infomation.'
		self.printLine()
		
		#type
		if not data['info'] == '':
			print 'Type        | ' + data['info']

		#hash and vary
		for hash in hashdata['hash']:
			ret += '"' + hash + '" + '
		print 'Hash        | ' + ret.rstrip('+ ')

		if len(hashdata['vary']) > 0:
			maxlen = self.chkMaxLength(hashdata['vary'],'key') + len('req.http.')
			self.printLine()
			for vary in hashdata['vary']:
				pad = ' ' * (maxlen - len('req.http.' + vary['key']))
				print 'Vary        | req.http.' + vary['key'] + pad + ' | ' + vary['val']

		#length
		print 'Object size | ' + str(data['length'])

		#backend
		print 'Backend     | ' + data['backendname']
		
		self.printLine()
		print





	def printAction(self,base,idx):
		data = base['data'][idx]['act']

		max = 6 # return

		self.printLine('#')
		print 'Action infomation.'

			
		self.printLine()

		for v in data:
			length = self.chkMaxLength(v['item'],'key');
			if max < length:
				max = length

		for v in data:
			self._sub_printAction_Box(v['function'])
			self._sub_printAction_Line(v,max)
		print
		
	def _sub_printAction_Line(self , data, max):
		item = data['item']
		ret  = data['return']
		print '      |'
		if len(item) > 0:
			for v in item:
				pad = ' ' * (max - len(v['key']))
				print '      | ' + v['key'] + pad +' | ' + v['val']
		pad = ' ' * (max - 6)
		print '      | ' + max * ' ' + ' |'
		print '      | return' + pad + ' | ' + ret
		print '      |'

	def _sub_printAction_Box(self,txt):
		df  = 13 - len(txt)
		spa = ' ' * (df // 2)
		spb = ' ' * ((df // 2) + (df % 2))
		
		print '+-------------+'
		print '|'+spa+txt+spb+'|'
		print '+-------------+'

	def printVariable(self,base,idx):
		data = base['data'][idx]['var']
		prn  = []
		
		for key in self.prnVarOrder:
			self._sub_printVariable(data,key,prn)

		if len(prn) > 0:
			maxLen    = self.chkMaxLength(prn, 'key')
			maxLenVal = self.chkMaxLength(prn, 'val')
			
			lineLen = (maxLen + maxLenVal + len(' | '))

			self.printLine('#')
			print 'Variable infomation.'
			self.printLine('-',lineLen)
			for v in prn:
				if v == 0:
					self.printLine('-',lineLen)
				else:
					self.printPad(v['key'], v['val'], maxLen)
			print

	def _sub_printVariable(self,data,key,prn):
		if not data.has_key(key):
			return prn
		obj = data[key].items()
		for cat,v in obj:
			for vv in v:
				prn.append({
					'key' : (key + '.' + cat + '.' + vv['key']).strip('.'),
					'val' : vv['val']
					})
		prn.append(0)
		return prn

	def printLine(self, char = '-' ,length = 70):
		print char * length
		
	def printPad(self,k, v, maxLen , dlm = " | "):
		fmt    = "%- " + str(maxLen) + "s" + dlm + "%s"
		print fmt % (k , v)
	
	def chkMaxLength(self, data, key=''):
		maxLen = 0
		if isinstance(data, list):
			for v in data:
				if isinstance(v, dict) and v.has_key(key):
					length = len(v[key])
					if maxLen < length:
						maxLen = length
		else:
			for k,v in data.items():
				length = len(k)
				if maxLen < length:
					maxLen = length
		return maxLen
	
	#client.*��server.*��ݒ�iserver�̓f�[�^�����Ȃ��̂ŁE�E�E�j
	def setVarClientServer(self,base):
		data   = base['data']
		for var in data:
			var['client'] = {
				'ip' : [{
					'key'  : '',
					'lkey' : '',
					'val'  : base['client']['ip'],
					}]
				}

	#�^�O�̖��̒ǉ�
	def apdTagName(self,raw):
		for v in raw:
			v['tagname'] = self.tags[v['type']][v['tag']]
	
	#�g�����U�N�V�������Ƃ̃f�[�^�쐬
	def conTrx(self,r):
		if not r:
			return
		#�l���쐬
		type = r['type']
		if type == 0:
			return
		
		tag  = r['tag']
		fd   = r['fd']
		if self.obj[type].has_key(fd):
			#�J���Ă�
			if self.reqsep[type]['close'].has_key(tag):
				#����(Print�Ώہj
				self.obj[type][fd][-1]['raw'].append(r)

				self.commitTrx(type,fd)
				self.printTrx(type,fd)
				if type == 1:
					#�f�[�^�폜(Client�̏ꍇ�̂�)
					del self.obj[type][fd]
			elif self.reqsep[type]['open'].has_key(tag):
				if type == 1: #client
					#�J���i�o�b�N�G���h����������̃o�O�j
					del self.obj[type][fd]
					self.obj[type][fd] = [{'raw' : []}]
					self.obj[type][fd][-1]['raw'].append(r)
				elif type == 2:#Backend
					#�J���i�o�b�N�G���h����������̃o�O�j
					#ESI�Ή��Ŏg��ꂽ���̃`�F�b�N���s��
					#del self.obj[type][fd]
					self.obj[type][fd].append({'raw' : []})
					self.obj[type][fd][-1]['raw'].append(r)

			else:
				#�ʏ�i�[
				self.obj[type][fd][-1]['raw'].append(r)
		elif self.reqsep[type]['open'].has_key(tag):
			#�J��
			self.obj[type][fd] = [{'raw':[]}]
			self.obj[type][fd][-1]['raw'].append(r)

	#�X���b�h����̏���
	def sighandler(self,event, signr, handler):
		event.set()
		
	def vapLoop(self,event):
		while not event.isSet():
			self.vap.VSL_NonBlockingDispatch(self.vapCallBack)
			time.sleep(0.1)
		self.endthread = True


	def fileLoop(self,event):
		if not os.path.exists(self.logfile):
			self.endthread = True
			return

		f = open(self.logfile)
		for line in f.readlines():
			self.vslData.append(self.parseFile(line))
		f.close()
		self.endthread = True





	def printLoop(self,event):
		while not event.isSet():
			if len(self.vslData) == 0:
				
				if self.endthread:
					break
				time.sleep(0.1)
				continue
			while 1:
				if len(self.vslData) == 0:
					break
				self.conTrx( self.vslData.pop(0) )
			if self.endthread:
				break
	

	def startThread(self,inloop):
		threads = []
		e = threading.Event()
		signal.signal(signal.SIGINT, (lambda a, b: self.sighandler(e, a, b)))

		# �X���b�h�쐬
		#if self.vap:
		threads.append(threading.Thread(target=inloop, args=(e,)))
		threads[-1].start()
		
		threads.append(threading.Thread(target=self.printLoop, args=(e,)))
		threads[-1].start()

		# �I���҂�
		for th in threads:
			while th.isAlive():
				time.sleep(0.5)
			th.join()

		
	def attachVarnishAPI(self):
		self.vap = varnishapi.VarnishAPI(self.libvap)

	def vapCallBack(self,priv, tag, fd, length, spec, ptr, bm):
		self.vslData.append(self.vap.normalizeDic(priv, tag, fd, length, spec, ptr, bm))

	def parseFile(self, data):
		'''
		{'fd': 0L,
		 'msg': 'Wr 200 19 PONG 1367695724 1.0',
		 'tag': 'CLI',
		 'type': 0L,
		 'typeName': '-'}
		�f�[�^��ǂݍ��ޏꍇ
		 1284 RxHeader     b Content-Type: image/png

		'''
		m = self.rfmt.search(data.strip())

		if not m:
			return

		r = {
			'fd'       : int(m.group(1)),
			'msg'      : m.group(4),
			'tag'      : m.group(2),
			'typeName' : m.group(3),
			}

		if r['typeName'] == '-':
			r['type'] = 0
		elif r['typeName'] == 'c':
			r['type'] = 1
		elif r['typeName'] == 'b':
			r['type'] = 2
		self.vslData.append(r)

		
	def __init__(self):
		self.rfmt = re.compile('^([^ ]+) +([^ ]+) +([^ ]+) +(.*)$')
		
		self.filter     = {#��Ŋ֐��ɂ���
			0:{},
			#Client
			1:{
				#"Debug"				:"",
				#"Error"				:"",
				#"CLI"				:"",
				#"StatSess"			:"",
				"ReqEnd"			: self.filterReqEnd,
				#"SessionOpen"		:"",
				#"SessionClose"		:"",
				#"BackendOpen"		:"",
				#"BackendXID"		:"",
				#"BackendReuse"		:"",
				#"BackendClose"		:"",
				#"HttpGarbage"		:"",
				"Backend"			: self.filterBackend,
				"Length"			: self.filterLength,
				"FetchError"		: self.filterError,
				"RxRequest"			: self.filterRequest,
				#"RxResponse"		:"",
				#"RxStatus"			:"",
				"RxURL"				: self.filterRequest,
				"RxProtocol"		: self.filterRequest,
				"RxHeader"			: self.filterRequest,
				#"TxRequest"			:"",
				"TxResponse"		: self.filterRequest,
				"TxStatus"			: self.filterRequest,
				#"TxURL"				:"",
				"TxProtocol"		: self.filterRequest,
				"TxHeader"			: self.filterRequest,
				#"ObjRequest"		:"",
				"ObjResponse"		: self.filterRequest,
				#"ObjStatus"			:"",
				#"ObjURL"			:"",
				"ObjProtocol"		: self.filterRequest,
				"ObjHeader"			: self.filterRequest,
				#"LostHeader"		:"",
				#"TTL"				:"",
				#"Fetch_Body"		:"",
				#"VCL_acl"			:"",
				"VCL_call"			: self.filterAction,
				"VCL_trace"			: [self.filterTrace, self.filterActItem],
				"VCL_return"		: self.filterAction,
				#"VCL_error"			:"",
				"ReqStart"			: self.filterReqStart,
				#"Hit"				:"",
				#"HitPass"			:"",
				#"ExpBan"			:"",
				#"ExpKill"			:"",
				#"WorkThread"		:"",
				"ESI_xmlerror"		: self.filterError,
				"Hash"				: [self.filterHash, self.filterActItem],
				#"Backend_health"	:"",
				"VCL_Log"			: self.filterActItem,
				#"Gzip"				:"",
			},
			#Backend
			2:{
				#"Debug"				:"",
				#"Error"				:"",
				#"CLI"				:"",
				#"StatSess"			:"",
				#"ReqEnd"			:"",
				#"SessionOpen"		:"",
				#"SessionClose"		:"",
				#"BackendOpen"		:"",
				#"BackendXID"		:"",
				#"BackendReuse"		:"",
				#"BackendClose"		:"",
				#"HttpGarbage"		:"",
				#"Backend"			:"",
				"Length"			: self.filterLength,
				#"FetchError"		:"",
				#"RxRequest"			:"",
				"RxResponse"		: self.filterRequest,
				"RxStatus"			: self.filterRequest,
				"RxURL"				: self.filterRequest,
				"RxProtocol"		: self.filterRequest,
				"RxHeader"			: self.filterRequest,
				"TxRequest"			: self.filterRequest,
				#"TxResponse"		:"",
				#"TxStatus"			:"",
				"TxURL"				: self.filterRequest,
				"TxProtocol"		: self.filterRequest,
				"TxHeader"			: self.filterRequest,
				#"ObjRequest"		:"",
				#"ObjResponse"		:"",
				#"ObjStatus"			:"",
				#"ObjURL"			:"",
				#"ObjProtocol"		:"",
				#"ObjHeader"			:"",
				#"LostHeader"		:"",
				#"TTL"				:"",
				#"Fetch_Body"		:"",
				#"VCL_acl"			:"",
				#"VCL_call"			:"",
				#"VCL_trace"			:"",
				#"VCL_return"		:"",
				#"VCL_error"			:"",
				#"ReqStart"			:"",
				#"Hit"				:"",
				#"HitPass"			:"",
				#"ExpBan"			:"",
				#"ExpKill"			:"",
				#"WorkThread"		:"",
				#"ESI_xmlerror"		:"",
				#"Hash"				:"",
				#"Backend_health"	:"",
				#"VCL_Log"			:"",
				#"Gzip"				:"",
			},
		}
		self.vslutil = varnishapi.VSLUtil()
		self.tags    = self.vslutil.tags
		
		
	def runVSL(self):
		self.attachVarnishAPI()
		self.startThread(self.vapLoop)

	def runFILE(self,file):
		self.logfile = file
		self.attachVarnishAPI()
		self.startThread(self.fileLoop)
		
		


#---------------------------------------------------------------------------------------------------
# ref:http://tomoemon.hateblo.jp/entry/20090921/p1
from pprint import pprint
import types

def var_dump(obj):
  pprint(dump(obj))

def dump(obj):
  '''return a printable representation of an object for debugging'''
  newobj = obj
  if isinstance(obj, list):
    # ���X�g�̒��g��\���ł���`���ɂ���
    newobj = []
    for item in obj:
      newobj.append(dump(item))
  elif isinstance(obj, tuple):
    # �^�v���̒��g��\���ł���`���ɂ���
    temp = []
    for item in obj:
      temp.append(dump(item))
    newobj = tuple(temp)
  elif isinstance(obj, set):
    # �Z�b�g�̒��g��\���ł���`���ɂ���
    temp = []
    for item in obj:
      # item��class�̏ꍇ��dump()�͎�����Ԃ���,������set�Ŏg�p�ł��Ȃ��̂ŕ�����ɂ���
      temp.append(str(dump(item)))
    newobj = set(temp)
  elif isinstance(obj, dict):
    # �����̒��g�i�L�[�A�l�j��\���ł���`���ɂ���
    newobj = {}
    for key, value in obj.items():
      # key��class�̏ꍇ��dump()��dict��Ԃ���,dict�̓L�[�ɂȂ�Ȃ��̂ŕ�����ɂ���
      newobj[str(dump(key))] = dump(value)
  elif isinstance(obj, types.FunctionType):
    # �֐���\���ł���`���ɂ���
    newobj = repr(obj)
  elif '__dict__' in dir(obj):
    # �V�����`���̃N���X class Hoge(object)�̃C���X�^���X��__dict__�������Ă���
    newobj = obj.__dict__.copy()
    if ' object at ' in str(obj) and not '__type__' in newobj:
      newobj['__type__']=str(obj).replace(" object at ", " #").replace("__main__.", "")
    for attr in newobj:
      newobj[attr]=dump(newobj[attr])
  return newobj

#---------------------------------------------------------------------------------------------------

main()