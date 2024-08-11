#!/usr/bin/env python
"""
    Marko Pinteric 2020

    RA6963 그래픽 LCD 컨트롤러
        - 초고속 병렬 통신을 위한 C 코드 사용
        - 동일한 폴더에 parallel.so가 필요함
        - 빠른 전송을 위해 데이터는 연속적인 바이트 블록으로 제공되어야 함
        - 읽기 및 쓰기를 지원하며, 읽기는 선택 사항임
        - 백라이트 제어, PWM은 dtoverlay 방식을 사용함

    PWM dtoverlay 방식
        - "/boot/config.txt"에 "dtoverlay=pwm,pin=<pin>,func=<func>"을 추가

        GPIO 핀    PWM 채널    기능          설명
        12          0           4 (ALT0)
        13          1           4 (ALT0)
        18          0           2 (ALT5)    모든 Raspberry Pi에서 작동함
        19          1           2 (ALT5)

    자세한 정보는: http://www.pinteric.com/displays.html을 참조
"""

import os, numpy, time
from ctypes import cdll, c_ubyte, c_void_p, c_int, c_uint, c_uint8, c_uint16, c_uint64

##### C 라이브러리 래핑 #####

parallel = cdll.LoadLibrary("./parallel.so")

"""
deinitialise(object)

칩의 인스턴스를 제거합니다. 프로그램 종료 시 권장되지만 필수는 아닙니다.
인수: 칩 인스턴스의 포인터
"""
deinitialise = parallel.deinitialise
deinitialise.argtypes = [c_void_p]

"""
object = initialise(d7, d6, d5, d4, d3, d2, d1, d0, rscd, enwr, rwrd, protocol, tsetup, tclock, tread, tproc, thold)

디바이스의 인스턴스를 생성합니다.
인수: 8개의 데이터 라인, RS/CD, EN/WR, RW/RD 제어 라인, 프로토콜, 5개의 대기 시간
반환: 칩 인스턴스의 포인터
GPIO 번호가 범위를 벗어나면 -> 정의되지 않은 라인; D3/D2/D1/D0 정의되지 않으면 -> 4비트 통신; RWRD 정의되지 않으면 -> 칩에 쓰기 전용
"""
initialise = parallel.initialise
initialise.restype = c_void_p
initialise.argtypes = [c_int, c_int, c_int, c_int, c_int, c_int, c_int, c_int, c_int, c_int, c_int, c_int, c_int, c_int, c_int, c_int, c_int]

"""
readdata(object, [datapos], datanum)

다수의 데이터를 읽습니다.
인수: 칩 인스턴스의 포인터, 데이터 배열의 포인터, 읽을 데이터 수
POINTER(c_ubyte), c_char_p -> c_void_p
"""
readdata = parallel.readdata
readdata.argtypes = [c_void_p, c_void_p, c_int]

"""
readregister(object)

레지스터를 읽습니다.
인수: 칩 인스턴스의 포인터
반환: 레지스터 값
"""
readregister = parallel.readregister
readregister.argtypes = [c_void_p]

"""
writecommand(object, datacom)

명령을 씁니다.
인수: 칩 인스턴스의 포인터, 명령 값
"""
writecommand = parallel.writecommand
writecommand.argtypes = [c_void_p, c_ubyte]

"""
writedata(object, [datapos], datanum)

대량의 데이터를 씁니다.
인수: 칩 인스턴스의 포인터, 데이터 배열의 포인터, 쓸 데이터 수
"""
writedata = parallel.writedata
writedata.argtypes = [c_void_p, c_void_p, c_int]

"""
gpioSetMode(gpio, mode)

GPIO 모드를 설정합니다.
"""
PI_OUTPUT = 1
PI_ALT0 = 4
PI_ALT5 = 2
gpioSetMode = parallel.gpioSetMode
gpioSetMode.argtypes = [c_uint, c_uint]

"""
gpioWrite(gpio, level)

GPIO에 값을 씁니다.
"""
gpioWrite = parallel.gpioWrite
gpioWrite.argtypes = [c_uint, c_uint]

# PWM 상수
PWMPATH = '/sys/class/pwm/pwmchip0'
PWMPER = 100000 # 주기(나노초 단위), 10kHz

##### RA6946 상수 #####

# 명령
LCD_SETCURSORPOINTER       = 0x21
LCD_SETOFFSETREGISTER      = 0x22
LCD_SETADDRESSPOINTER      = 0x24
LCD_SETTEXTHOMEADDRESS     = 0x40
LCD_SETTEXTAREA            = 0x41
LCD_SETGRAPHICHOMEADDRESS  = 0x42
LCD_SETGRAPHICAREA         = 0x43
LCD_MODESET                = 0x80
LCD_DISPLAYMODE            = 0x90
LCD_CURSORPATTERNSELECT    = 0xA0
LCD_DATAWRITEINCREMENT     = 0xC0
LCD_DATAREADINCREMENT      = 0xC1
LCD_DATAWRITEDECREMENT     = 0xC2
LCD_DATAEREADDECREMENT     = 0xC2
LCD_DATAWRITENONVARIABLE   = 0xC4
LCD_DATAREADNONVARIABLE    = 0xC4
LCD_SETDATAAUTOWRITE       = 0xB0
LCD_SETDATAAUTOREAD        = 0xB1
LCD_AUTORESET              = 0xB2
LCD_SCREENPEEK             = 0xE0
LCD_SCREENCOPY             = 0xE8
LCD_BITRESET               = 0xF0
LCD_BITSET                 = 0xF8
LCD_SCREENREVERSE          = 0xD0
LCD_BLINKTIME              = 0x50
LCD_CURSORAUTOMOVING       = 0x60
LCD_CGROMFONTSELECT        = 0x70

# LCD_MODESET 옵션
LCD_OR                     = 0x00
LCD_EXOR                   = 0x01
LCD_AND                    = 0x03
LCD_TEXTATTRIBUTE          = 0x04
LCD_EXTERNALCGROM          = 0x08

# LCD_DISPLAYMODE 옵션
LCD_CURSORBLINK            = 0x01
LCD_CURSORON               = 0x02
LCD_TEXTON                 = 0x04
LCD_GRAPHICON              = 0x08

##### RA6946 함수 #####

# 칩을 초기화합니다. 매개변수:
#     화면의 가로 및 세로 크기
#     D7, D6, D5, D4, D3, D2, D1, D0, RST, CD, WR, RD(선택적) 라인 GPIO 핀
#     백라이트 전원 GPIO 핀(선택적)
#     초기 백라이트 값 (0-1)
#     백라이트 전원 GPIO 핀 PWM 활성화
#     텍스트, 그래픽 및 문자 생성기용 사용자 지정 홈 주소(선택적)
# GPIO 핀 값이 범위를 벗어나면(0-27) -> 옵션 사용되지 않음
class RA6963(object):
    def __init__(self, pixx, pixy, d7, d6, d5, d4, d3, d2, d1, d0, rst, cd, wr, rd=-1, bl=-1,  backlight=1.0, pwm=False, addr=None):
        self._pixx = pixx  # LCD의 가로 해상도
        self._pixy = pixy  # LCD의 세로 해상도
        self._rst = rst  # 리셋 핀
        self._pwm = pwm  # PWM 사용 여부
        self.addr = addr  # 사용자 지정 주소 (옵션)
        # 화면 속성
        self.inhibit = 0x03
        self.reverse = 0x05
        self.bold = 0x07
        self.blink = 0x08
        # 하드웨어 기본값
        self._displaymode = 0
        # 소프트웨어 기본값
        self._modeset = 0

        # 매뉴얼에 따른 설정: tsetup, tclock, tread, tproc, thold = 20, 80, 150, 80, 50
        self._dev = initialise(d7, d6, d5, d4, d3, d2, d1, d0, cd, wr, rd, 8080, 20, 2000, 300, 1000, 2000)

        # 백라이트 전원 설정
        if (bl>=0 and bl<=27):
            if pwm == False: gpioSetMode(bl, PI_OUTPUT)
            else:
                if not os.path.isdir(PWMPATH):
                    print('PWM 초기화 안됨.')
                    bl = -1
                if (bl==12 or bl==18): self._pwmchan = 0
                elif (bl==13 or bl==19): self._pwmchan = 1
                else:
                    print('GPIO%d는 PWM 하드웨어 핀이 아님.' % bl)
                    bl = -1
                if (bl != -1):
                    if (bl==12 or bl==13): gpioSetMode(bl, PI_ALT0)
                    if (bl==18 or bl==19): gpioSetMode(bl, PI_ALT5)
                    self._path = PWMPATH + '/pwm%d' % self._pwmchan
                    if not os.path.isdir(self._path):
                        with open(PWMPATH + '/export', 'w') as f: f.write('%d' % self._pwmchan)
                    time.sleep(0.1) # 안정화 대기
                    with open(self._path + '/period', 'w') as f: f.write('%d' % PWMPER)
        self._bl=bl
        if (bl>=0 and bl<=27):
            self.setbacklight(backlight)

        # 칩 초기화
        gpioWrite(self._rst, 1)
        gpioSetMode(self._rst, PI_OUTPUT)
        self.startup()

    # 시작 절차, 칩을 재설정할 때 사용할 수 있음
    def startup(self):
        # 리셋

        gpioWrite(self._rst, 0)
        gpioWrite(self._rst, 1)

        # 텍스트, 그래픽 및 문자 생성기 위치 설정
        if self.addr==None:
            self.textaddress=0x0000
            self.graphicaddress=0x1000
            self.cgaddress=0x7800
        else:
            self.textaddress=self.addr[0]
            self.graphicaddress=self.addr[1]
            self.cgaddress=self.addr[2]

        temp = (c_uint16.__ctype_le__ *1) (self.textaddress)
        writedata(self._dev, temp, 2)
        writecommand(self._dev, LCD_SETTEXTHOMEADDRESS)

        temp = (c_uint16.__ctype_le__ *1) (self._pixx//8)
        writedata(self._dev, temp, 2)
        writecommand(self._dev, LCD_SETTEXTAREA)

        temp = (c_uint16.__ctype_le__ *1) (self.graphicaddress)
        writedata(self._dev, temp, 2)
        writecommand(self._dev, LCD_SETGRAPHICHOMEADDRESS)

        temp = (c_uint16.__ctype_le__ *1) (self._pixx//8)
        writedata(self._dev, temp, 2)
        writecommand(self._dev, LCD_SETGRAPHICAREA)

        if (self.cgaddress & 0x07FF) > 0:
            print('지정된 CG 주소가 잘못됨. 더 낮은 올바른 주소로 반올림 중...')
            self.cgaddress = self.cgaddress & 0xF800
        temp = (c_uint16.__ctype_le__ *1) (self.cgaddress >> 11)
        writedata(self._dev, temp, 2)
        writecommand(self._dev, LCD_SETOFFSETREGISTER)

    # 칩 종료
    def close(self):
        if (self._bl>=0 and self._bl<=27 and self._pwm==True):
            if os.path.isdir(self._path):
                with open(PWMPATH + '/unexport', 'w') as f: f.write('%d' % self._pwmchan)
        deinitialise(self._dev)

    # 현재 포인터 위치에서 비트 리셋, 매개변수: 0-7
    def bitreset(self,num):
        writecommand(self._dev, LCD_BITRESET | num)

    # 현재 포인터 위치에서 비트 설정, 매개변수: 0-7
    def bitset(self,num):
        writecommand(self._dev, LCD_BITSET | num)

    # 깜박임 속도 설정, 매개변수: 0-7
    def blinktime(self,num):
        temp = (c_uint16.__ctype_le__ *1) (num)
        writedata(self._dev, temp, 2)
        writecommand(self._dev, LCD_BLINKTIME)

    # 문자 생성기 홈으로 포인터를 설정하고 주소를 반환
    def cghome(self):
        temp = (c_uint16.__ctype_le__ *1) (self.cgaddress)
        writedata(self._dev, temp, 2)
        writecommand(self._dev, LCD_SETADDRESSPOINTER)
        return(self.cgaddress)

    # CGROM 폰트 선택, 매개변수: 1-2
    def cgromfont(self, num):
        if num==1: temp = (c_uint16.__ctype_le__ *1) (0x0002)
        else: temp = (c_uint16.__ctype_le__ *1) (0x0003)
        writedata(self._dev, temp, 2)
        writecommand(self._dev, LCD_CGROMFONTSELECT)

    # 그래픽, 텍스트 및 문자 생성기 메모리 초기화
    def clearall(self):
        self.graphichome()
        temp = numpy.zeros(shape=(self._pixx*self._pixy//8,), dtype=numpy.int8)
        writecommand(self._dev, LCD_SETDATAAUTOWRITE)
        writedata(self._dev, temp.ctypes.data_as(c_void_p), self._pixx*self._pixy//8)
        writecommand(self._dev, LCD_AUTORESET)
        self.texthome()
        writecommand(self._dev, LCD_SETDATAAUTOWRITE)
        writedata(self._dev, temp.ctypes.data_as(c_void_p), self._pixx*self._pixy//64)
        writecommand(self._dev, LCD_AUTORESET)
        self.cghome()
        writecommand(self._dev, LCD_SETDATAAUTOWRITE)
        writedata(self._dev, temp.ctypes.data_as(c_void_p), 2048)
        writecommand(self._dev, LCD_AUTORESET)

    # 커서 깜박임 변경, 매개변수: 불리언
    def cursorblink(self, blink):
        if blink: self._displaymode = self._displaymode | LCD_CURSORBLINK
        else: self._displaymode = self._displaymode & ~LCD_CURSORBLINK
        writecommand(self._dev, LCD_DISPLAYMODE | self._displaymode)

    # 커서 표시 변경, 매개변수: 불리언
    def cursordisplay(self, display):
        if display: self._displaymode = self._displaymode | LCD_CURSORON
        else: self._displaymode = self._displaymode & ~LCD_CURSORON
        writecommand(self._dev, LCD_DISPLAYMODE | self._displaymode)

    # 커서 이동 변경, 매개변수: 불리언
    def cursormove(self, move):
        if move: self._displaymode = writecommand(self._dev, LCD_CURSORAUTOMOVING | 0x00)
        else: self._displaymode = writecommand(self._dev, LCD_CURSORAUTOMOVING | 0x01)

    # 커서 패턴 선택, 매개변수: 0-7
    def cursorpattern(self, patt):
        writecommand(self._dev, LCD_CURSORPATTERNSELECT | patt)

    # 사용자 정의 문자 쓰기(첫 128개는 미리 정의됨), 매개변수: c_uint64 목록, 첫 문자의 위치
    def definechars(self, chars, location = 0):
        self.setaddress(self.cgaddress+128*8 + location*8)
        writecommand(self._dev, LCD_SETDATAAUTOWRITE)
        for i in chars:
            temp = (c_uint64.__ctype_be__ *1) (i)
            writedata(self._dev, temp, 8)
        writecommand(self._dev, LCD_AUTORESET)

    # 디스플레이 모드 변경, 매개변수: 불리언 (텍스트), 불리언 (그래픽)
    def displaymode(self, text, graphic):
        if text: self._displaymode = self._displaymode | LCD_TEXTON
        else: self._displaymode = self._displaymode & ~LCD_TEXTON
        if graphic: self._displaymode = self._displaymode | LCD_GRAPHICON
        else: self._displaymode = self._displaymode & ~LCD_GRAPHICON
        writecommand(self._dev, LCD_DISPLAYMODE | self._displaymode)

    # 외부 문자 생성기 사용, 매개변수: 불리언
    def externalcg(self, bool):
        if bool: self._modeset = self._modeset | LCD_EXTERNALCGROM
        else: self._modeset = self._modeset & ~LCD_EXTERNALCGROM
        writecommand(self._dev, LCD_MODESET | self._modeset)

    # 그래픽 홈으로 포인터를 설정하고 주소를 반환
    def graphichome(self):
        temp = (c_uint16.__ctype_le__ *1) (self.graphicaddress)
        writedata(self._dev, temp, 2)
        writecommand(self._dev, LCD_SETADDRESSPOINTER)
        return(self.graphicaddress)

    # 모드 설정 변경, 매개변수: 1-4 (OR, EXOR, AND, 텍스트 속성)
    def modeset(self, mode):
        self._modeset = self._modeset & ~(LCD_OR | LCD_EXOR | LCD_AND | LCD_TEXTATTRIBUTE)
        if mode==1: self._modeset = self._modeset | LCD_OR
        if mode==2: self._modeset = self._modeset | LCD_EXOR
        if mode==3: self._modeset = self._modeset | LCD_AND
        if mode==4: self._modeset = self._modeset | LCD_TEXTATTRIBUTE
        writecommand(self._dev, LCD_MODESET | self._modeset)

    # 다수의 데이터 읽기, 매개변수: 포인터, 길이
    def readdata(self, datapos, datanum):
        writecommand(self._dev, LCD_SETDATAAUTOREAD)
        readdata(self._dev, datapos, datanum)
        writecommand(self._dev, LCD_AUTORESET)

    # 데이터를 읽고, 포인터 위치를 감소시킴
    def readdecrement(self):
        temp = (c_uint8 *1) ()
        writecommand(self._dev, LCD_DATAREADDECREMENT)
        readdata(self._dev, temp, 1)
        return(temp[0])

    # 데이터를 읽고, 포인터 위치를 증가시킴
    def readincrement(self):
        temp = (c_uint8 *1) ()
        writecommand(self._dev, LCD_DATAREADINCREMENT)
        readdata(self._dev, temp, 1)
        return(temp[0])

    # 상태 읽기
    def readstatus(self):
        temp = readregister(self._dev)
        return(temp)

    # 데이터를 읽고, 포인터 위치를 변경하지 않음
    def readonvariable(self):
        temp = (c_uint8 *1) ()
        writecommand(self._dev, LCD_DATAREADNONVARIABLE)
        readdata(self._dev, temp, 1)
        return(temp[0])

    # 단일 라스터 라인의 데이터를 그래픽 영역으로 복사 - 단일 모드에서 사용 가능
    def screencopy(self):
        writecommand(self._dev, LCD_SCREENCOPY)

    # 화면에서 위치를 확인 - 하드웨어 열 번호와 소프트웨어 열 번호가 같을 때 사용 가능
    def screenpeek(self):
        temp = (c_uint8 *1) ()
        writecommand(self._dev, LCD_SCREENPEEK)
        readdata(self._dev, temp, 1)
        return(temp[0])

    # 화면 반전, 매개변수: 불리언
    def screenreverse(self,bool):
        if bool: writecommand(self._dev, LCD_SCREENREVERSE,1,1)
        else: writecommand(self._dev, LCD_SCREENREVERSE,1,0)

    # 현재 포인터 주소 설정
    def setaddress(self, value):
        temp = (c_uint16.__ctype_le__ *1) (value)
        writedata(self._dev, temp, 2)
        writecommand(self._dev, LCD_SETADDRESSPOINTER)

    # 백라이트 설정 변경
    def setbacklight(self, backlight):
        if (self._bl>=0 and self._bl<=27):
            if self._pwm == False:
                if(backlight>0): gpioWrite(self._bl, 1)
                else: gpioWrite(self._bl, 0)
            else:
                if backlight> 0:
                    with open(self._path + '/duty_cycle', 'w') as f: f.write('%d' % int(backlight*PWMPER))
                    with open(self._path + '/enable', 'w') as f: f.write('1')
                else:
                    with open(self._path + '/enable', 'w') as f: f.write('0')

    # 현재 포인터 주소 설정
    def setcursor(self, xaddr, yaddr):
        temp = (c_uint16.__ctype_le__ *2) (256 * yaddr + xaddr)
        writedata(self._dev, temp, 2)
        writecommand(self._dev, LCD_SETCURSORPOINTER)

    # 텍스트 홈 주소 변경, 매개변수: 0x0000 - 0xFFFF
    def settexthome(self, value):
        self.textaddress=value
        temp = (c_uint16.__ctype_le__ *1) (value)
        writedata(self._dev, temp, 2)
        writecommand(self._dev, LCD_SETTEXTHOMEADDRESS)

    # 그래픽 홈 주소 변경, 매개변수: 0x0000 - 0xFFFF
    def setgraphichome(self, value):
        self.graphicaddress=value
        temp = (c_uint16.__ctype_le__ *1) (value)
        writedata(self._dev, temp, 2)
        writecommand(self._dev, LCD_SETGRAPHICHOMEADDRESS)

    # 텍스트 홈으로 포인터를 설정하고 주소 반환
    def texthome(self):
        temp = (c_uint16.__ctype_le__ *1) (self.textaddress)
        writedata(self._dev, temp, 2)
        writecommand(self._dev, LCD_SETADDRESSPOINTER)
        return(self.textaddress)

    # 데이터 쓰기: 매개변수: 포인터, 길이
    def writedata(self, datapos, datanum):
        writecommand(self._dev, LCD_SETDATAAUTOWRITE)
        writedata(self._dev, datapos, datanum)
        writecommand(self._dev, LCD_AUTORESET)

    # 데이터를 쓰고, 포인터 위치를 감소시킴
    def writedecrement(self, value):
        temp = (c_uint8 *1) (value)
        writedata(self._dev, temp, 1)
        writecommand(self._dev, LCD_DATAWRITEDECREMENT)

    # 데이터를 쓰고, 포인터 위치를 증가시킴
    def writeincrement(self, value):
        temp = (c_uint8 *1) (value)
        writedata(self._dev, temp, 1)
        writecommand(self._dev, LCD_DATAWRITEINCREMENT)

    # 데이터를 쓰고, 포인터 위치를 변경하지 않음
    def writeonvariable(self, value):
        temp = (c_uint8 *1) (value)
        writedata(self._dev, temp, 1)
        writecommand(self._dev, LCD_DATAWRITENONVARIABLE)

    # 전체 화면 ASCII 텍스트 쓰기, 매개변수: 포인터
    def writetext(self, text):
        temp=bytearray(text.replace("\n", ""))
        for i in range(len(temp)):
            temp[i] = temp[i] - 32
        text = str(temp)
        self.texthome()
        writecommand(self._dev, LCD_SETDATAAUTOWRITE)
        writedata(self._dev, text, len(text))
        writecommand(self._dev, LCD_AUTORESET)
