from pygame import time as pytime
import time
import random
import math

try:
	import launchpad_py as launchpad
except ImportError:
	try:
		import launchpad
	except ImportError:
		sys.exit("error loading launchpad.py")

class LaunchpadScalemode:

	# Constants
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

	WHITE_KEYS = MUSICAL_MODES['Major']

	NOTE_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

	NOTE_COLORS = { 
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

	# Settings
	note_callback = None
	func_button_callback = None

	# State Variables
	_launchpad_model = None
	lp = None
	_pressed_notes = []
	_pressed_buttons = []
	_grid_musical_mode = 'Major'
	_grid_octave = 3
	_grid_key = 0
	_launchpad_mode = "notes" # possible values are "notes" and "settings"

	def __init__( self ):
		print("LaunchpadScalemode Initialized!")

	def start( self ):
		self.discover_launchpad(True)
		self._main_loop()
		
	def discover_launchpad(self, keep_checking=False):
		# create an instance
		self.lp = launchpad.Launchpad()
		while self._launchpad_model is None:
			# lp.ListAll()
			# check what we have here and override lp if necessary
			if self.lp.Check( 0, "pro" ):
				self.lp = launchpad.LaunchpadPro()
				if self.lp.Open():
					print("Launchpad Pro")
					self._launchpad_model = "Pro"
					
			elif self.lp.Check( 0, "mk2" ):
				self.lp = launchpad.LaunchpadMk2()
				if self.lp.Open():
					print("Launchpad Mk2")
					self._launchpad_model = "Mk2"    
			else:
				if self.lp.Open():
					print("Launchpad Mk1/S/Mini")
					self._launchpad_model = "Mk1"

			if self._launchpad_model is None:
				if keep_checking is False:
					print("Did not find any Launchpads, meh...")					
					return
				else:
					time.sleep(2)

	def _main_loop(self):
		self.lp.ButtonFlush()
		self.lp.Reset()

		self._color_buttons()

		randomButton = None
		randomButtonCounter = 0
		randomButtonModeEnabled = False

		while True:
			time.sleep(0.005) # 5ms wait between loops
			but = self.lp.ButtonStateXY()

			if randomButtonModeEnabled:
				if randomButtonCounter > 30:
					if randomButton:
						self._button_released(randomButton[0], randomButton[1])  
						randomButton = None
					# Make a new randomButton
					randomButton = [random.randint(1,8), random.randint(1,8)]
					self._button_pressed(randomButton[0], randomButton[1], 100)
					randomButtonCounter = 0
				randomButtonCounter = randomButtonCounter + 1

			if but != []:
				x = but[0] + 1
				y = (8 - but[1]) + 1
				pressed = (but[2] > 0) or (but[2] == True)

				if self._launchpad_mode is "notes":
					if (x < 9) and (y < 9):
						if pressed:
							velocity = 100
							if self._launchpad_model is "Pro":
								velocity = but[2]
							self._button_pressed(x, y, velocity)
						else:
							self._button_released(x, y)
					elif x == 9 and y == 1 and pressed:
						# Clear screen
						self.lp.Reset()
					elif x == 9 and y == 2:
						# Random button mode
						if pressed:
							randomButtonModeEnabled = True
							randomButton = None
							randomButtonCounter = 0
						else:
							randomButtonModeEnabled = False
							if randomButton:
								self._button_released(randomButton[0], randomButton[1])
								randomButton = None
				if self._launchpad_mode is "settings":
					if (((1 <= x < 8) and (y == 6)) or ((x in [1, 2, 4, 5, 6]) and y == 7)) and pressed:
						# Grid Key
						self._grid_key = self.WHITE_KEYS[x - 1] + (y == 7)
						self._color_buttons()
						print "Key is ", self.NOTE_NAMES[self._grid_key]
				if x in [1, 2] and y == 9 and pressed:
					self.func_button_callback(x, y, pressed)
				elif x is 9 and y == 7:
					if pressed:
						self._launchpad_mode = "settings"
						self.lp.Reset()
						self._color_buttons()
					else:
						self._launchpad_mode = "notes"
						self._color_buttons()
				elif x == 9 and y == 6 and pressed:
					if self._grid_octave < 8:
						self._grid_octave += 1
				elif x == 9 and y == 5 and pressed:
					if self._grid_octave > 0:
						self._grid_octave -= 1
				
				print(" event: ", but, x, y)

	def _color_note_button(self, x, y, rootNote=False, pressed=False):
		if pressed:
			key = "pressed"
		elif rootNote:
			key = "root"
		else:
			key = "default"

		self._color_button(x, y, key)

	def _color_button(self, x, y, buttonType):
		lpX = x - 1
		lpY = -1 * (y - 9)

		if self._launchpad_model is "Mk1":
			colorSet = "Mk1"
			self.lp.LedCtrlXY(lpX, lpY, self.NOTE_COLORS[self._launchpad_model][buttonType][0], self.NOTE_COLORS[self._launchpad_model][buttonType][1])
		else:
			colorSet = "Mk2"
			self.lp.LedCtrlXY(lpX, lpY, self.NOTE_COLORS[colorSet][buttonType][0], self.NOTE_COLORS[colorSet][buttonType][1], self.NOTE_COLORS[colorSet][buttonType][2])

	def _color_buttons(self):
		if self._launchpad_mode is "notes":
			for x in range(1, 9):
				for y in range(1, 9):
					noteInfo = self._get_note_info(x, y)
					scaleNoteNumber = noteInfo[2]
					self._color_note_button(x, y, (scaleNoteNumber == 0), (noteInfo[0] in self._pressed_notes))
		elif self._launchpad_mode is "settings":
			self._color_button(1, 6, "settingsKeyOn" if self._grid_key is 0 else "settingsKeyOff")                
			self._color_button(1, 7, "settingsKeyOn" if self._grid_key is 1 else "settingsKeyOff")                
			self._color_button(2, 6, "settingsKeyOn" if self._grid_key is 2 else "settingsKeyOff")                
			self._color_button(2, 7, "settingsKeyOn" if self._grid_key is 3 else "settingsKeyOff")                
			self._color_button(3, 6, "settingsKeyOn" if self._grid_key is 4 else "settingsKeyOff")
			self._color_button(4, 6, "settingsKeyOn" if self._grid_key is 5 else "settingsKeyOff")
			self._color_button(4, 7, "settingsKeyOn" if self._grid_key is 6 else "settingsKeyOff")
			self._color_button(5, 6, "settingsKeyOn" if self._grid_key is 7 else "settingsKeyOff")
			self._color_button(5, 7, "settingsKeyOn" if self._grid_key is 8 else "settingsKeyOff")
			self._color_button(6, 6, "settingsKeyOn" if self._grid_key is 9 else "settingsKeyOff")
			self._color_button(6, 7, "settingsKeyOn" if self._grid_key is 10 else "settingsKeyOff")
			self._color_button(7, 6, "settingsKeyOn" if self._grid_key is 11 else "settingsKeyOff")

		self._color_button(1, 9, "pressed") # sample down
		self._color_button(2, 9, "pressed") # sample up
		self._color_button(9, 6, "pressed") # octave up
		self._color_button(9, 5, "pressed") # octave down
		self._color_button(9, 7, "pressed") # settings

	def _get_note_info(self, x, y):
		base8NoteNumber = (x-1) + (3 * (y-1))
		noteOctave = int(math.floor(base8NoteNumber / 7))
		scaleNoteNumber = base8NoteNumber % 7
		midiNote = ((self._grid_octave + 1) * 12) + self._grid_key + self.MUSICAL_MODES[self._grid_musical_mode][scaleNoteNumber] + 12 * noteOctave
		return [midiNote, noteOctave, scaleNoteNumber]

	def diff(first, second):
		second = set(second)
		return [item for item in first if item not in second]

	def _get_buttons_for_midi_note(self, midiNote):
		buttons = []
		for x in range(1, 9):
			for y in range(1, 9):
				noteInfo = self._get_note_info(x, y)
				if noteInfo[0] == midiNote:
					buttons.append([x, y])
		return buttons

	def get_currently_playing_midi_notes(self):
		midiNotes = []
		for buttonNumber in self._pressed_buttons:
			x = int(math.floor(buttonNumber % 8)) + 1
			y = (buttonNumber / 8) + 1
			noteInfo = self._get_note_info(x, y)
			if noteInfo[0] not in midiNotes:
				midiNotes.append(noteInfo[0])
		return midiNotes

	# This takes 1-based coordinates with 1,1 being the lower left button
	def _button_pressed(self, x, y, velocity):
		buttonNumber = (x-1)  + ((y-1) * 8)
		noteInfo = self._get_note_info(x, y)
		midiNote = noteInfo[0]
		scaleNoteNumber = noteInfo[2]

		self._pressed_buttons.append(buttonNumber)

		self.note_callback("note_on", midiNote, velocity)
		if midiNote not in self._pressed_notes:
			buttons = self._get_buttons_for_midi_note(midiNote)
			for newButton in buttons:
				self._color_note_button(newButton[0], newButton[1], (scaleNoteNumber == 0), True)
			self._pressed_notes.append(midiNote)
		# print "Button Pressed", buttonNumber, "with MIDI note number", midiNote
		# print "Pressed Notes", _pressed_notes
		return

	# This takes 1-based coordinates with 1,1 being the lower left button
	def _button_released(self, x, y):
		buttonNumber = (x-1)  + ((y-1) * 8)
		noteInfo = self._get_note_info(x, y)
		midiNote = noteInfo[0]

		# Question: what new notes (not buttons) are now no longer being pressed 
		self._pressed_buttons.remove(buttonNumber)
		
		new_pressed_notes = self.get_currently_playing_midi_notes()

		if midiNote not in new_pressed_notes:
			self.note_callback('note_off', midiNote, 0)
			buttons = self._get_buttons_for_midi_note(midiNote)
			for newButton in buttons:
				noteInfo = self._get_note_info(newButton[0], newButton[1])
				scaleNoteNumber = noteInfo[2]
				self._color_note_button(newButton[0], newButton[1], (scaleNoteNumber == 0))

		# newlyReleasedNotes = diff(_pressed_notes, new_pressed_notes)
		# print("released notes: ", newlyReleasedNotes)
		# for newlyReleaseMidiNote in newlyReleasedNotes:
		#     MidiCallback([0b10000001, newlyReleaseMidiNote, 100], None)
		#     buttons = _get_buttons_for_midi_note(newlyReleaseMidiNote)
		#     for newButton in buttons:
		#         noteInfo = _get_note_info(newButton[0], newButton[1])
		#         scaleNoteNumber = noteInfo[2]
		#         _color_note_button(newButton[0], newButton[1], (scaleNoteNumber == 0))
		self._pressed_notes = new_pressed_notes
		# print "Pressed Notes", new_pressed_notes
		return
