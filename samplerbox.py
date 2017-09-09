#
#  SamplerBox
#
#  author:    Joseph Ernest (twitter: @JosephErnest, mail: contact@samplerbox.org)
#  url:       http://www.samplerbox.org/
#  license:   Creative Commons ShareAlike 3.0 (http://creativecommons.org/licenses/by-sa/3.0/)
#
#  samplerbox.py: Main file
#


#########################################
# LOCAL
# CONFIG
#########################################

AUDIO_DEVICE_ID = 1                     # change this number to use another soundcard
SAMPLES_DIR = "."                       # The root directory containing the sample-sets. Example: "/media/" to look for samples on a USB stick / SD card
USE_SERIALPORT_MIDI = False             # Set to True to enable MIDI IN via SerialPort (e.g. RaspberryPi's GPIO UART pins)
USE_I2C_7SEGMENTDISPLAY = False         # Set to True to use a 7-segment display via I2C
USE_LAUNCHPAD = True                    # Set to True to add support for Launchpad
USE_BUTTONS = False                     # Set to True to use momentary buttons (connected to RaspberryPi's GPIO pins) to change preset
MAX_POLYPHONY = 80                      # This can be set higher, but 80 is a safe value

USE_I2C_16X2DISPLAY = False				# Set to True to use a 16x2 display via I2C
										# Define some device parameters
I2C_16x2DISPLAY_ADDR  = 0x3f 			# I2C device address
I2C_16x2DISPLAY_LCD_WIDTH = 16   		# Maximum characters per line

#########################################
# IMPORT
# MODULES
#########################################

import wave
import time
import numpy
import os
import re
import sounddevice
import threading
from chunk import Chunk
import struct
import rtmidi_python as rtmidi
import samplerbox_audio
import random


#########################################
# SLIGHT MODIFICATION OF PYTHON'S WAVE MODULE
# TO READ CUE MARKERS & LOOP MARKERS
#########################################

class waveread(wave.Wave_read):

    def initfp(self, file):
        self._convert = None
        self._soundpos = 0
        self._cue = []
        self._loops = []
        self._ieee = False
        self._file = Chunk(file, bigendian=0)
        if self._file.getname() != 'RIFF':
            raise Error, 'file does not start with RIFF id'
        if self._file.read(4) != 'WAVE':
            raise Error, 'not a WAVE file'
        self._fmt_chunk_read = 0
        self._data_chunk = None
        while 1:
            self._data_seek_needed = 1
            try:
                chunk = Chunk(self._file, bigendian=0)
            except EOFError:
                break
            chunkname = chunk.getname()
            if chunkname == 'fmt ':
                self._read_fmt_chunk(chunk)
                self._fmt_chunk_read = 1
            elif chunkname == 'data':
                if not self._fmt_chunk_read:
                    raise Error, 'data chunk before fmt chunk'
                self._data_chunk = chunk
                self._nframes = chunk.chunksize // self._framesize
                self._data_seek_needed = 0
            elif chunkname == 'cue ':
                numcue = struct.unpack('<i', chunk.read(4))[0]
                for i in range(numcue):
                    id, position, datachunkid, chunkstart, blockstart, sampleoffset = struct.unpack('<iiiiii', chunk.read(24))
                    self._cue.append(sampleoffset)
            elif chunkname == 'smpl':
                manuf, prod, sampleperiod, midiunitynote, midipitchfraction, smptefmt, smpteoffs, numsampleloops, samplerdata = struct.unpack(
                    '<iiiiiiiii', chunk.read(36))
                for i in range(numsampleloops):
                    cuepointid, type, start, end, fraction, playcount = struct.unpack('<iiiiii', chunk.read(24))
                    self._loops.append([start, end])
            chunk.skip()
        if not self._fmt_chunk_read or not self._data_chunk:
            raise Error, 'fmt chunk and/or data chunk missing'

    def getmarkers(self):
        return self._cue

    def getloops(self):
        return self._loops


#########################################
# MIXER CLASSES
#
#########################################

class PlayingSound:

    def __init__(self, sound, note):
        self.sound = sound
        self.pos = 0
        self.fadeoutpos = 0
        self.isfadeout = False
        self.note = note

    def fadeout(self, i):
        self.isfadeout = True

    def stop(self):
        try:
            playingsounds.remove(self)
        except:
            pass


class Sound:

    def __init__(self, filename, midinote, velocity, seq):
        wf = waveread(filename)
        self.fname = filename
        self.midinote = midinote
        self.velocity = velocity
        self.seq = seq
        if wf.getloops():
            self.loop = wf.getloops()[0][0]
            self.nframes = wf.getloops()[0][1] + 2
        else:
            self.loop = -1
            self.nframes = wf.getnframes()

        self.data = self.frames2array(wf.readframes(self.nframes), wf.getsampwidth(), wf.getnchannels())

        wf.close()

    def play(self, note):
        snd = PlayingSound(self, note)
        playingsounds.append(snd)
        return snd

    def frames2array(self, data, sampwidth, numchan):
        if sampwidth == 2:
            npdata = numpy.fromstring(data, dtype=numpy.int16)
        elif sampwidth == 3:
            npdata = samplerbox_audio.binary24_to_int16(data, len(data)/3)
        if numchan == 1:
            npdata = numpy.repeat(npdata, 2)
        return npdata

FADEOUTLENGTH = 30000
FADEOUT = numpy.linspace(1., 0., FADEOUTLENGTH)            # by default, float64
FADEOUT = numpy.power(FADEOUT, 6)
FADEOUT = numpy.append(FADEOUT, numpy.zeros(FADEOUTLENGTH, numpy.float32)).astype(numpy.float32)
SPEED = numpy.power(2, numpy.arange(0.0, 84.0)/12).astype(numpy.float32)

samples = {}
playingnotes = {}
lastplayedseq = {}
sustainplayingnotes = []
sustain = False
playingsounds = []
globalvolume = 10 ** (-12.0/20)  # -12dB default global volume
globaltranspose = 0


#########################################
# AUDIO AND MIDI CALLBACKS
#
#########################################

def AudioCallback(outdata, frame_count, time_info, status):
    global playingsounds
    rmlist = []
    playingsounds = playingsounds[-MAX_POLYPHONY:]
    b = samplerbox_audio.mixaudiobuffers(playingsounds, rmlist, frame_count, FADEOUT, FADEOUTLENGTH, SPEED)
    for e in rmlist:
        try:
            playingsounds.remove(e)
        except:
            pass
    b *= globalvolume
    outdata[:] = b.reshape(outdata.shape)

def MidiCallback(message, time_stamp):
    global playingnotes, sustain, sustainplayingnotes, lastplayedseq
    global preset
    messagetype = message[0] >> 4
    messagechannel = (message[0] & 15) + 1
    note = message[1] if len(message) > 1 else None
    midinote = note
    velocity = message[2] if len(message) > 2 else None

    if messagetype == 9 and velocity == 0:
        messagetype = 8

    if messagetype == 9:    # Note on
        midinote += globaltranspose
        try:
            # Get the list of available samples for this note and velocity
            notesamples = samples[midinote, velocity]
            
            # Choose a sample from the list
            sample = random.choice (notesamples)
            
            # If we have no value for lastplayedseq, set it to 0
            lastplayedseq.setdefault(midinote, 0)

            # If we have more than 2 samples to work with, reject duplicates
            if len(notesamples) >= 3:
                while sample.seq == lastplayedseq[midinote]:
                    sample = random.choice (notesamples)

            # print "About to play midinote: %s, seq: %s" % (midinote, sample.seq)
            playingnotes.setdefault(midinote, []).append(sample.play(midinote))
            # Recorded the last played note
            lastplayedseq[midinote] = sample.seq
        except:
            pass

    elif messagetype == 8:  # Note off
        midinote += globaltranspose
        if midinote in playingnotes:
            for n in playingnotes[midinote]:
                if sustain:
                    sustainplayingnotes.append(n)
                else:
                    n.fadeout(50)
            playingnotes[midinote] = []

    elif messagetype == 12:  # Program change
        print 'Program change ' + str(note)
        preset = note
        LoadSamples()

    elif (messagetype == 11) and (note == 64) and (velocity < 64):  # sustain pedal off
        for n in sustainplayingnotes:
            n.fadeout(50)
        sustainplayingnotes = []
        sustain = False

    elif (messagetype == 11) and (note == 64) and (velocity >= 64):  # sustain pedal on
        sustain = True


#########################################
# LOAD SAMPLES
#
#########################################

LoadingThread = None
LoadingInterrupt = False


def LoadSamples():
    global LoadingThread
    global LoadingInterrupt

    if LoadingThread:
        LoadingInterrupt = True
        LoadingThread.join()
        LoadingThread = None

    LoadingInterrupt = False
    LoadingThread = threading.Thread(target=ActuallyLoad)
    LoadingThread.daemon = True
    LoadingThread.start()

NOTES = ["c", "c#", "d", "d#", "e", "f", "f#", "g", "g#", "a", "a#", "b"]


def ActuallyLoad():
    global preset
    global samples
    global playingsounds
    global globalvolume, globaltranspose
    playingsounds = []
    samples = {}
    globalvolume = 10 ** (-12.0/20)  # -12dB default global volume
    globaltranspose = 0

    samplesdir = SAMPLES_DIR if os.listdir(SAMPLES_DIR) else '.'      # use current folder (containing 0 Saw) if no user media containing samples has been found

    basename = next((f for f in os.listdir(samplesdir) if f.startswith("%d " % preset)), None)      # or next(glob.iglob("blah*"), None)
    if basename:
        dirname = os.path.join(samplesdir, basename)
    if not basename:
        print 'Preset empty: %s' % preset
        display("E%03d" % preset)
        lcd_string('%s Preset Empty' % preset, 1)
        return
    print 'Preset loading: %s (%s)' % (preset, basename)
    display("L%03d" % preset)
    lcd_string('%s' % (basename), 1)
    lcd_string('Loading...', 2)

    definitionfname = os.path.join(dirname, "definition.txt")
    if os.path.isfile(definitionfname):
        with open(definitionfname, 'r') as definitionfile:
            for i, pattern in enumerate(definitionfile):
                try:
                    if r'%%volume' in pattern:        # %%paramaters are global parameters
                        globalvolume *= 10 ** (float(pattern.split('=')[1].strip()) / 20)
                        continue
                    if r'%%transpose' in pattern:
                        globaltranspose = int(pattern.split('=')[1].strip())
                        continue
                    defaultparams = {'midinote': '0', 'velocity': '127', 'notename': '', 'seq': 1}
                    if len(pattern.split(',')) > 1:
                        defaultparams.update(dict([item.split('=') for item in pattern.split(',', 1)[1].replace(' ', '').replace('%', '').split(',')]))
                    pattern = pattern.split(',')[0]
                    pattern = re.escape(pattern.strip())
                    pattern = pattern.replace(r"\%midinote", r"(?P<midinote>\d+)").replace(r"\%velocity", r"(?P<velocity>\d+)")\
                                     .replace(r"\%seq", r"(?P<seq>\d+)")\
                                     .replace(r"\%notename", r"(?P<notename>[A-Ga-g]#?[0-9])").replace(r"\*", r".*?").strip()    # .*? => non greedy
                    for fname in os.listdir(dirname):
                        if LoadingInterrupt:
                            return
                        m = re.match(pattern, fname)
                        if m:
                            info = m.groupdict()
                            midinote = int(info.get('midinote', defaultparams['midinote']))
                            velocity = int(info.get('velocity', defaultparams['velocity']))
                            seq = int(info.get('seq', defaultparams['seq']))
                            notename = info.get('notename', defaultparams['notename'])
                            
                            if notename:
                                midinote = NOTES.index(notename[:-1].lower()) + (int(notename[-1])+2) * 12
                            # print "Loaded note %s, velocity %s, seq %s." % (midinote, velocity, seq)
                            if (midinote, velocity) in samples:
                                samples[midinote, velocity].append(Sound(os.path.join(dirname, fname), midinote, velocity, seq))
                            else: 
                                samples[midinote, velocity] = [Sound(os.path.join(dirname, fname), midinote, velocity, seq)]
                except:
                    print "Error in definition file, skipping line %s." % (i+1)

    else:
        for midinote in range(0, 127):
            if LoadingInterrupt:
                return
            file = os.path.join(dirname, "%d.wav" % midinote)
            if os.path.isfile(file):
                samples[midinote, 127] = [ Sound(file, midinote, 127, 1) ]

    initial_keys = set(samples.keys())
    for midinote in xrange(128):
        lastvelocity = None
        for velocity in xrange(128):
            if (midinote, velocity) not in initial_keys:
                samples[midinote, velocity] = lastvelocity
            else:
                if not lastvelocity:
                    for v in xrange(velocity):
                        samples[midinote, v] = samples[midinote, velocity]
                lastvelocity = samples[midinote, velocity]
        if not lastvelocity:
            for velocity in xrange(128):
                try:
                    samples[midinote, velocity] = samples[midinote-1, velocity]
                except:
                    pass
    if len(initial_keys) > 0:
        print 'Preset loaded: ' + str(preset)
        display("%04d" % preset)
        lcd_string('%s' % (basename), 1)
        lcd_string('', 2)
    else:
        print 'Preset empty: ' + str(preset)
        display("E%03d" % preset)
        lcd_string('%s Preset Empty' % (preset), 1)
	

#########################################
# OPEN AUDIO DEVICE
#
#########################################

try:
    sd = sounddevice.OutputStream(device=AUDIO_DEVICE_ID, blocksize=512, samplerate=44100, channels=2, dtype='int16', callback=AudioCallback)
    sd.start()
    print 'Opened audio device #%i' % AUDIO_DEVICE_ID
except:
    print 'Invalid audio device #%i' % AUDIO_DEVICE_ID
    exit(1)


#########################################
# BUTTONS THREAD (RASPBERRY PI GPIO)
#
#########################################

if USE_BUTTONS:
    import RPi.GPIO as GPIO

    lastbuttontime = 0

    def Buttons():
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(18, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(17, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        global preset, lastbuttontime
        while True:
            now = time.time()
            if not GPIO.input(18) and (now - lastbuttontime) > 0.2:
                lastbuttontime = now
                preset -= 1
                if preset < 0:
                    preset = 127
                LoadSamples()

            elif not GPIO.input(17) and (now - lastbuttontime) > 0.2:
                lastbuttontime = now
                preset += 1
                if preset > 127:
                    preset = 0
                LoadSamples()

            time.sleep(0.020)

    ButtonsThread = threading.Thread(target=Buttons)
    ButtonsThread.daemon = True
    ButtonsThread.start()


#########################################
# 7-SEGMENT DISPLAY
#
#########################################

if USE_I2C_7SEGMENTDISPLAY:
    import smbus

    bus = smbus.SMBus(1)     # using I2C

    def display(s):
        for k in '\x76\x79\x00' + s:     # position cursor at 0
            try:
                bus.write_byte(0x71, ord(k))
            except:
                try:
                    bus.write_byte(0x71, ord(k))
                except:
                    pass
            time.sleep(0.002)
            
    def lcd_string(s, line):
        pass

    display('----')
    time.sleep(0.5)

elif USE_I2C_16X2DISPLAY:
	
	import smbus

	# Define some device constants
	LCD_CHR = 1 # Mode - Sending data
	LCD_CMD = 0 # Mode - Sending command
	
	LCD_LINE_1 = 0x80 # LCD RAM address for the 1st line
	LCD_LINE_2 = 0xC0 # LCD RAM address for the 2nd line
	LCD_LINE_3 = 0x94 # LCD RAM address for the 3rd line
	LCD_LINE_4 = 0xD4 # LCD RAM address for the 4th line
	
	LCD_BACKLIGHT  = 0x08  # On
	#LCD_BACKLIGHT = 0x00  # Off
	
	ENABLE = 0b00000100 # Enable bit
	
	# Timing constants
	E_PULSE = 0.0005
	E_DELAY = 0.0005
	
	bus = smbus.SMBus(1)     # using I2C
	
	def lcd_init():
		# Initialise display
		lcd_byte(0x33,LCD_CMD) # 110011 Initialise
		lcd_byte(0x32,LCD_CMD) # 110010 Initialise
		lcd_byte(0x06,LCD_CMD) # 000110 Cursor move direction
		lcd_byte(0x0C,LCD_CMD) # 001100 Display On,Cursor Off, Blink Off 
		lcd_byte(0x28,LCD_CMD) # 101000 Data length, number of lines, font size
		lcd_byte(0x01,LCD_CMD) # 000001 Clear display
		time.sleep(E_DELAY)
		
	def lcd_byte(bits, mode):
	  # Send byte to data pins
	  # bits = the data
	  # mode = 1 for data
	  #        0 for command

	  bits_high = mode | (bits & 0xF0) | LCD_BACKLIGHT
	  bits_low = mode | ((bits<<4) & 0xF0) | LCD_BACKLIGHT

	  # High bits
	  bus.write_byte(I2C_16x2DISPLAY_ADDR, bits_high)
	  lcd_toggle_enable(bits_high)

	  # Low bits
	  bus.write_byte(I2C_16x2DISPLAY_ADDR, bits_low)
	  lcd_toggle_enable(bits_low)

	def lcd_toggle_enable(bits):
	  # Toggle enable
	  time.sleep(E_DELAY)
	  bus.write_byte(I2C_16x2DISPLAY_ADDR, (bits | ENABLE))
	  time.sleep(E_PULSE)
	  bus.write_byte(I2C_16x2DISPLAY_ADDR,(bits & ~ENABLE))
	  time.sleep(E_DELAY)
	  
	def lcd_string(message,line):
		if line == 1:
			line_address = LCD_LINE_1
		elif line == 2:
			line_address = LCD_LINE_2
		elif line == 3:
			line_address = LCD_LINE_3
		elif line == 4:
			line_address = LCD_LINE_4
		
		
		# Send string to display

		message = message.ljust(I2C_16x2DISPLAY_LCD_WIDTH," ")

		lcd_byte(line_address, LCD_CMD)

		for i in range(I2C_16x2DISPLAY_LCD_WIDTH):
			lcd_byte(ord(message[i]),LCD_CHR)
	
	def display(s):
		pass
	
	lcd_init()
	display('----')
	time.sleep(0.5)
	
else:

    def display(s):
        pass
    def lcd_string(s, line):
        pass


#########################################
# MIDI IN via SERIAL PORT
#
#########################################

if USE_SERIALPORT_MIDI:
    import serial

    ser = serial.Serial('/dev/ttyAMA0', baudrate=38400)       # see hack in /boot/cmline.txt : 38400 is 31250 baud for MIDI!

    def MidiSerialCallback():
        message = [0, 0, 0]
        while True:
            i = 0
            while i < 3:
                data = ord(ser.read(1))  # read a byte
                if data >> 7 != 0:
                    i = 0      # status byte!   this is the beginning of a midi message: http://www.midi.org/techspecs/midimessages.php
                message[i] = data
                i += 1
                if i == 2 and message[0] >> 4 == 12:  # program change: don't wait for a third byte: it has only 2 bytes
                    message[2] = 0
                    i = 3
            MidiCallback(message, None)

    MidiThread = threading.Thread(target=MidiSerialCallback)
    MidiThread.daemon = True
    MidiThread.start()


#########################################
# LAUNCHPAD SUPPORT
#
#########################################

if USE_LAUNCHPAD:
    
    from pygame import time as pytime

    try:
        import launchpad_py as launchpad
    except ImportError:
        try:
            import launchpad
        except ImportError:
            sys.exit("error loading launchpad.py")

    import random
    import math

    pressedNotes = []
    pressedButtons = []

    def LaunchpadCallback():
        global preset

        MUSICAL_MODES = {
            'Major':            [0, 2, 4, 5, 7, 9, 11],
            'Minor':            [0, 2, 3, 5, 7, 8, 10],
            'Dorian':           [0, 2, 3, 5, 7, 9, 10],
            'Mixolydian':       [0, 2, 4, 5, 7, 9, 10],
            'Lydian':           [0, 2, 4, 6, 7, 9, 11],
            'Phrygian':         [0, 1, 3, 5, 7, 8, 10],
            'Locrian':          [0, 1, 3, 5, 6, 8, 10],
            'Diminished':       [0, 1, 3, 4, 6, 7, 9, 10],

            'Whole-half':       [0, 2, 3, 5, 6, 8, 9, 11],
            'Whole Tone':       [0, 2, 4, 6, 8, 10],
            'Minor Blues':      [0, 3, 5, 6, 7, 10],
            'Minor Pentatonic': [0, 3, 5, 7, 10],
            'Major Pentatonic': [0, 2, 4, 7, 9],
            'Harmonic Minor':   [0, 2, 3, 5, 7, 8, 11],
            'Melodic Minor':    [0, 2, 3, 5, 7, 9, 11],
            'Super Locrian':    [0, 1, 3, 4, 6, 8, 10],

            'Bhairav':          [0, 1, 4, 5, 7, 8, 11],
            'Hungarian Minor':  [0, 2, 3, 6, 7, 8, 11],
            'Minor Gypsy':      [0, 1, 4, 5, 7, 8, 10],
            'Hirojoshi':        [0, 2, 3, 7, 8],
            'In-Sen':           [0, 1, 5, 7, 10],
            'Iwato':            [0, 1, 5, 6, 10],
            'Kumoi':            [0, 2, 3, 7, 9],
            'Pelog':            [0, 1, 3, 4, 7, 8],

            'Spanish':          [0, 1, 3, 4, 5, 6, 8, 10],
            'IonEol':           [0, 2, 3, 4, 5, 7, 8, 9, 10, 11]
        }
        gridMusicalMode = 'Major'
        gridOctave = 3
        gridKey = 0
        launchpadMode = "notes" # possible values are "notes" and "settings"
        noteColors = { 
            "Mk1": { 
                "pressed": [0, 63],    
                "root": [3, 0],      
                "default": [1, 1],
                "settingsKeyOff": [0, 4],
                "settingsKeyOn":  [0, 20],
            }, 
            "Mk2": { 
                "pressed": [0, 50, 0], 
                "root": [0, 10, 30], 
                "default": [10, 10, 15],
                "settingsKeyOff": [0, 4, 0],
                "settingsKeyOn":  [0, 20, 0],
            }
        }

        def ColorNoteButton(x, y, rootNote=False, pressed=False):
            if pressed:
                key = "pressed"
            elif rootNote:
                key = "root"
            else:
                key = "default"

            ColorLPButton(x, y, key)

        def ColorLPButton(x, y, buttonType):
            lpX = x - 1
            lpY = -1 * (y - 9)


            if launchpadModel == "Mk1":
                colorSet = "Mk1"
                lp.LedCtrlXY(lpX, lpY, noteColors[launchpadModel][buttonType][0], noteColors[launchpadModel][buttonType][1])
            else:
                colorSet = "Mk2"
                lp.LedCtrlXY(lpX, lpY, noteColors[colorSet][buttonType][0], noteColors[colorSet][buttonType][1], noteColors[colorSet][buttonType][2])


        def ColorLPButtons(lp):
            if launchpadMode is "notes":
                for x in range(1, 9):
                    for y in range(1, 9):
                        noteInfo = GetNoteInfo(x, y)
                        scaleNoteNumber = noteInfo[2]
                        ColorNoteButton(x, y, (scaleNoteNumber == 0), (noteInfo[0] in pressedNotes))
            elif launchpadMode is "settings":
                ColorLPButton(1, 6, "settingsKeyOn" if gridKey is 0 else "settingsKeyOff")                
                ColorLPButton(1, 7, "settingsKeyOn" if gridKey is 1 else "settingsKeyOff")                
                ColorLPButton(2, 6, "settingsKeyOn" if gridKey is 2 else "settingsKeyOff")                
                ColorLPButton(2, 7, "settingsKeyOn" if gridKey is 3 else "settingsKeyOff")                
                ColorLPButton(3, 6, "settingsKeyOn" if gridKey is 4 else "settingsKeyOff")
                ColorLPButton(4, 6, "settingsKeyOn" if gridKey is 5 else "settingsKeyOff")
                ColorLPButton(4, 7, "settingsKeyOn" if gridKey is 6 else "settingsKeyOff")
                ColorLPButton(5, 6, "settingsKeyOn" if gridKey is 7 else "settingsKeyOff")
                ColorLPButton(5, 7, "settingsKeyOn" if gridKey is 8 else "settingsKeyOff")
                ColorLPButton(6, 6, "settingsKeyOn" if gridKey is 9 else "settingsKeyOff")
                ColorLPButton(6, 7, "settingsKeyOn" if gridKey is 10 else "settingsKeyOff")
                ColorLPButton(7, 6, "settingsKeyOn" if gridKey is 11 else "settingsKeyOff")

            ColorLPButton(1, 9, "pressed") # sample down
            ColorLPButton(2, 9, "pressed") # sample up
            ColorLPButton(9, 6, "pressed") # octave up
            ColorLPButton(9, 5, "pressed") # octave down
            ColorLPButton(9, 7, "pressed") # settings

        def GetNoteInfo(x, y):
            base8NoteNumber = (x-1) + (3 * (y-1))
            noteOctave = int(math.floor(base8NoteNumber / 7))
            scaleNoteNumber = base8NoteNumber % 7
            midiNote = ((gridOctave + 1) * 12) + gridKey + MUSICAL_MODES[gridMusicalMode][scaleNoteNumber] + 12 * noteOctave
            return [midiNote, noteOctave, scaleNoteNumber]

        def diff(first, second):
                second = set(second)
                return [item for item in first if item not in second]

        def GetAllButtonsForMidiNote(midiNote):
            buttons = []
            for x in range(1, 9):
                for y in range(1, 9):
                    noteInfo = GetNoteInfo(x, y)
                    if noteInfo[0] == midiNote:
                        buttons.append([x, y])
            return buttons

        def GetCurrentlyPlayingMidiNotes():
            global pressedButtons
            midiNotes = []
            for buttonNumber in pressedButtons:
                x = int(math.floor(buttonNumber % 8)) + 1
                y = (buttonNumber / 8) + 1
                noteInfo = GetNoteInfo(x, y)
                if noteInfo[0] not in midiNotes:
                    midiNotes.append(noteInfo[0])
            return midiNotes

        # This takes 1-based coordinates with 1,1 being the lower left button
        def LaunchpadNoteButtonPressed(x, y, velocity):
            global pressedNotes, pressedButtons

            buttonNumber = (x-1)  + ((y-1) * 8)
            noteInfo = GetNoteInfo(x, y)
            midiNote = noteInfo[0]
            scaleNoteNumber = noteInfo[2]

            pressedButtons.append(buttonNumber)

            MidiCallback([0b10010001, midiNote, velocity], None)
            if midiNote not in pressedNotes:
                buttons = GetAllButtonsForMidiNote(midiNote)
                for newButton in buttons:
                    ColorNoteButton(newButton[0], newButton[1], (scaleNoteNumber == 0), True)
                pressedNotes.append(midiNote)
            # print "Button Pressed", buttonNumber, "with MIDI note number", midiNote
            # print "Pressed Notes", pressedNotes
            return

        # This takes 1-based coordinates with 1,1 being the lower left button
        def LaunchpadButtonReleased(x, y):
            global pressedNotes, pressedButtons
            buttonNumber = (x-1)  + ((y-1) * 8)
            noteInfo = GetNoteInfo(x, y)
            midiNote = noteInfo[0]

            # Question: what new notes (not buttons) are now no longer being pressed 
            pressedButtons.remove(buttonNumber)
            
            newPressedNotes = GetCurrentlyPlayingMidiNotes()

            if midiNote not in newPressedNotes:
                MidiCallback([0b10000001, midiNote, 0], None)
                buttons = GetAllButtonsForMidiNote(midiNote)
                for newButton in buttons:
                    noteInfo = GetNoteInfo(newButton[0], newButton[1])
                    scaleNoteNumber = noteInfo[2]
                    ColorNoteButton(newButton[0], newButton[1], (scaleNoteNumber == 0))

            # newlyReleasedNotes = diff(pressedNotes, newPressedNotes)
            # print("released notes: ", newlyReleasedNotes)
            # for newlyReleaseMidiNote in newlyReleasedNotes:
            #     MidiCallback([0b10000001, newlyReleaseMidiNote, 100], None)
            #     buttons = GetAllButtonsForMidiNote(newlyReleaseMidiNote)
            #     for newButton in buttons:
            #         noteInfo = GetNoteInfo(newButton[0], newButton[1])
            #         scaleNoteNumber = noteInfo[2]
            #         ColorNoteButton(newButton[0], newButton[1], (scaleNoteNumber == 0))
            pressedNotes = newPressedNotes
            # print "Pressed Notes", newPressedNotes
            return

        launchpadModel = None

        # create an instance
        lp = launchpad.Launchpad();

        while launchpadModel is None:
            # lp.ListAll()
            
            # check what we have here and override lp if necessary
            if lp.Check( 0, "pro" ):
                lp = launchpad.LaunchpadPro()
                if lp.Open():
                    print("Launchpad Pro")
                    launchpadModel = "Pro"
                    
            elif lp.Check( 0, "mk2" ):
                lp = launchpad.LaunchpadMk2()
                if lp.Open():
                    print("Launchpad Mk2")
                    launchpadModel = "Mk2"    
            else:
                if lp.Open():
                    print("Launchpad Mk1/S/Mini")
                    launchpadModel = "Mk1"

            if launchpadModel is None:
                print("Did not find any Launchpads, meh...")
                # return
                    
                time.sleep(2)


        
        lp.ButtonFlush()
        lp.Reset()
        ColorLPButtons(lp)

        randomButton = None
        randomButtonCounter = 0
        randomButtonModeEnabled = False

        while True:
            pytime.wait(5)
            but = lp.ButtonStateXY()

            if randomButtonModeEnabled:
                if randomButtonCounter > 30:
                    if randomButton:
                        LaunchpadButtonReleased(randomButton[0], randomButton[1])  
                        randomButton = None
                    # Make a new randomButton
                    randomButton = [random.randint(1,8), random.randint(1,8)]
                    LaunchpadNoteButtonPressed(randomButton[0], randomButton[1], 100)
                    randomButtonCounter = 0
                randomButtonCounter = randomButtonCounter + 1

            if but != []:
                x = but[0] + 1
                y = (8 - but[1]) + 1
                pressed = (but[2] > 0) or (but[2] == True)

                if launchpadMode is "notes":
                    if (but[0] < 8) and (but[1] != 0):
                        if pressed:
                            velocity = 100
                            if launchpadModel is "Pro":
                                velocity = but[2]
                            LaunchpadNoteButtonPressed(x, y, velocity)
                        else:
                            LaunchpadButtonReleased(x, y)
                    elif but[0] == 8 and but[1] == 8 and (but[2] == 127 or but[2] == True):
                        # Clear screen
                        lp.Reset()
                    elif but[0] == 8 and but[1] == 7:
                        # Random button mode
                        if but[2] > 0 or but[2] == True:
                            randomButtonModeEnabled = True
                            randomButton = None
                            randomButtonCounter = 0
                        elif but[2] == 0 or but[2] == False:
                            randomButtonModeEnabled = False
                            if randomButton:
                                LaunchpadButtonReleased(randomButton[0], randomButton[1])
                                randomButton = None
                if launchpadMode is "settings":
                    if (((0 <= but[0] < 7) and (but[1] == 3)) or ((but[0] in [0, 1, 3, 4, 5]) and but[1] == 2)) and (but[2] == 127 or but[2] == True):
                        gridKey = MUSICAL_MODES['Major'][but[0]] + (but[1] == 2)
                        ColorLPButtons(lp)
                        print "Key is ", NOTES[gridKey]
                if but[0] == 0 and but[1] == 0 and (but[2] == 127 or but[2] == True):
                    preset -= 1
                    if preset < 0:
                        preset = 127
                    LoadSamples()
                elif but[0] == 1 and but[1] == 0 and (but[2] == 127 or but[2] == True):
                    preset += 1
                    if preset > 127:
                        preset = 0
                    LoadSamples()
                elif but[0] == 8 and but[1] == 2:
                    if but[2] == 127 or but[2] == True:
                        launchpadMode = "settings"
                        lp.Reset()
                        ColorLPButtons(lp)
                    elif but[2] == 0 or but[2] == False:
                        launchpadMode = "notes"
                        ColorLPButtons(lp)
                elif but[0] == 8 and but[1] == 3 and (but[2] == 127 or but[2] == True):
                    if gridOctave < 8:
                        gridOctave += 1
                elif but[0] == 8 and but[1] == 4 and (but[2] == 127 or but[2] == True):
                    if gridOctave > 0:
                        gridOctave -= 1
                
                
                print(" event: ", but, but[0]+1, (8 - but[1]) + 1)

    LaunchpadThread = threading.Thread(target=LaunchpadCallback)
    LaunchpadThread.daemon = True
    LaunchpadThread.start()


#########################################
# LOAD FIRST SOUNDBANK
#
#########################################

preset = 0
LoadSamples()


#########################################
# MIDI DEVICES DETECTION
# MAIN LOOP
#########################################

midi_in = [rtmidi.MidiIn()]
previous = []
while True:
    for port in midi_in[0].ports:
        if port not in previous and 'Midi Through' not in port and 'Launchpad' not in port:
            midi_in.append(rtmidi.MidiIn())
            midi_in[-1].callback = MidiCallback
            midi_in[-1].open_port(port)
            print 'Opened MIDI: ' + port
    previous = midi_in[0].ports
    time.sleep(2)
