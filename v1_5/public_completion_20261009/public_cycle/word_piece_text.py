#!/usr/bin/env python3
"""Read MS-DOC main-story text via CFB streams and the documented CLX piece table.

This is a text companion, not a Word layout/table parser. All CFB sector
chains and stream/FIB/CLX bounds are checked; no model or data rows are used
to decide which source text is extracted.
"""
import hashlib,json,struct
from pathlib import Path

FREE=0xffffffff;END=0xfffffffe
def u16(b,p):return struct.unpack_from('<H',b,p)[0]
def u32(b,p):return struct.unpack_from('<I',b,p)[0]

class CFB:
    def __init__(self,data):
        self.data=data
        if data[:8]!=bytes.fromhex('d0cf11e0a1b11ae1'):raise ValueError('Not a CFB file')
        self.size=1<<u16(data,30);self.mini=1<<u16(data,32)
        if self.size not in (512,4096) or self.mini!=64:raise ValueError('Unexpected CFB sector size')
        # Some public Word writers omit unused padding of the final sector.
        # Permit that sector, but return only bytes physically present; every
        # declared stream and text-piece size is still checked independently.
        self.limit=(len(data)+self.size-1)//self.size-1
        difat=list(struct.unpack_from('<109I',data,76));sid=u32(data,68);seen=set()
        for _ in range(u32(data,72)):
            if sid in seen:raise ValueError('DIFAT cycle')
            seen.add(sid);sector=self.sector(sid);entries=struct.unpack('<'+str(self.size//4)+'I',sector);difat.extend(entries[:-1]);sid=entries[-1]
        fats=[x for x in difat if x not in (FREE,END)][:u32(data,44)]
        if len(fats)!=u32(data,44):raise ValueError('FAT count mismatch')
        self.fat=[]
        for x in fats:self.fat.extend(struct.unpack('<'+str(self.size//4)+'I',self.sector(x)))
        directory=self.chain(u32(data,48),self.fat)
        self.entries={};self.root=None
        for i in range(0,len(directory),128):
            entry=directory[i:i+128]
            if len(entry)!=128:raise ValueError('Directory size invalid')
            count=u16(entry,64)
            if not count:continue
            if count>64 or count%2:raise ValueError('Directory name length invalid')
            name=entry[:count-2].decode('utf-16le');kind=entry[66]
            rec={'name':name,'kind':kind,'start':u32(entry,116),'size':struct.unpack_from('<Q',entry,120)[0]}
            if u16(data,26)==3:rec['size']&=0xffffffff
            if kind==5:self.root=rec
            elif kind==2:self.entries[name]=rec
        self.cutoff=u32(data,56);self.minifat=[];self.ministream=b''
        if u32(data,64):
            b=self.chain(u32(data,60),self.fat);self.minifat=list(struct.unpack('<'+str(len(b)//4)+'I',b))
        if self.root:self.ministream=self.chain(self.root['start'],self.fat)[:self.root['size']]
    def sector(self,sid):
        if sid>=self.limit:raise ValueError('Sector out of bounds')
        return self.data[(sid+1)*self.size:(sid+2)*self.size]
    def chain(self,sid,fat,mini=False):
        out=[];seen=set()
        while sid not in (END,FREE):
            if sid in seen or sid>=len(fat):raise ValueError('Sector chain cycle or invalid pointer')
            seen.add(sid)
            if mini:
                start=sid*self.mini;part=self.ministream[start:start+self.mini]
                if len(part)!=self.mini:raise ValueError('Mini sector outside root stream')
                out.append(part)
            else:out.append(self.sector(sid))
            sid=fat[sid]
        return b''.join(out)
    def stream(self,name):
        r=self.entries[name];b=self.chain(r['start'],self.minifat,True) if r['size']<self.cutoff else self.chain(r['start'],self.fat)
        if len(b)<r['size']:raise ValueError('Stream chain shorter than declared size')
        return b[:r['size']]

def extract(path):
    data=Path(path).read_bytes();cfb=CFB(data);word=cfb.stream('WordDocument')
    if u16(word,0)!=0xa5ec:raise ValueError('FIB Word magic not valid')
    flags=u16(word,10)
    if flags&(1<<8) or flags&(1<<15):raise ValueError('Encrypted/obfuscated DOC is unsupported')
    table_name='1Table' if flags&(1<<9) else '0Table';table=cfb.stream(table_name)
    pos=32;csw=u16(word,pos);pos+=2+csw*2;cslw=u16(word,pos);pos+=2
    if cslw<4:raise ValueError('FIB main-story length not present')
    main_count=u32(word,pos+12);pos+=cslw*4;pair_count=u16(word,pos);pos+=2
    if pair_count<=33:raise ValueError('FIB fcClx/lcbClx not present')
    fc=u32(word,pos+33*8);size=u32(word,pos+33*8+4)
    if fc+size>len(table):raise ValueError('CLX outside Table stream')
    clx=table[fc:fc+size];p=0
    while p<len(clx) and clx[p]==1:p+=3+u16(clx,p+1)
    if p+5>len(clx) or clx[p]!=2:raise ValueError('CLX has no Pcdt')
    length=u32(clx,p+1);plc=clx[p+5:p+5+length]
    if len(plc)!=length or (length-4)%12:raise ValueError('PlcPcd size invalid')
    count=(length-4)//12;cps=list(struct.unpack_from('<'+str(count+1)+'I',plc,0))
    if cps[0]!=0 or any(x>y for x,y in zip(cps,cps[1:])) or cps[-1]<main_count:raise ValueError('CLX character positions invalid')
    pieces=[];total_units=0
    for i in range(count):
        if cps[i]>=main_count:break
        units=min(cps[i+1],main_count)-cps[i];raw_fc=u32(plc,4*(count+1)+8*i+2)
        compressed=bool(raw_fc&(1<<30));offset=raw_fc&0x3fffffff
        if compressed:offset//=2
        byte_count=units if compressed else units*2
        if offset+byte_count>len(word):raise ValueError('Piece outside WordDocument stream')
        raw=word[offset:offset+byte_count]
        text=raw.decode('cp1252' if compressed else 'utf-16le',errors='strict')
        pieces.append(text);total_units+=units
    if total_units!=main_count:raise ValueError('Extracted main-story UTF16 unit count differs from FIB')
    raw=''.join(pieces);display=raw.replace('\r','\n').replace('\x07','\t').replace('\x0b','\n').replace('\x0c','\n\n')
    proof={'source_sha256':hashlib.sha256(data).hexdigest(),'reader':'bounded CFB and MS-DOC CLX main-story pieces; no layout reconstruction','fib_nFib':u16(word,2),'table_stream':table_name,'main_story_utf16_units':main_count,'extracted_main_story_units':total_units,'piece_count_total':count,'piece_count_main_story':len(pieces),'word_stream_sha256':hashlib.sha256(word).hexdigest(),'table_stream_sha256':hashlib.sha256(table).hexdigest(),'independent_table_enumeration':False}
    return display,proof

if __name__=='__main__':
    import sys
    text,proof=extract(sys.argv[1]);Path(sys.argv[2]).write_text(text,encoding='utf-8');Path(sys.argv[3]).write_text(json.dumps(proof,ensure_ascii=False,indent=2));print(json.dumps(proof,ensure_ascii=False))
