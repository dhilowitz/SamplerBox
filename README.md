SamplerBox
==========

NOTE: This is a fork of Joseph Ernest's SamplerBox project with two new additions:

1. Support for randomizing samples
2. Support for 16x2 display's via I2C. 


## Randomizing samples

You can now have multiple versions of the same sample. In order to specify an alternate version of the same sample, you number them and specify the `%seq` keyword. For example, let's say you have a sample set that contains three versions of A3 as follows:

		A1-1.wav
		A1-2.wav
		A1-3.wav
		A1-4.wav
		B1-1.wav
		...

You would specify a definition.txt that looks like this:

	%notename-%seq.wav

Each time the note A1 is hit, SamplerBox will choose randomly between the different A1 samples (making sure not to repeat any two consecutively).

## 16x2 Display with backpack

This code works with Hitachi HD44780 16x2 displays with PCF8574 backpack. These are super cheap ($6.00, including shipping) on eBay. In order to get this to work, you have to set the bus address in the I2C_16x2DISPLAY_ADDR variable of samplerbox.py. The address differs depending on which version of the backpack you have: If you have the PCF8574T, the default I2C bus address is 0x27. If you have the PCF8574AT the default I2C bus address is 0x3F. 

A handy set of utilities called I2CTools are used to probe the I2C bus. These can be installed with:

		sudo apt-get install i2c-tools

You can figure out the bus address for your device by doing this:

		sudo i2cdetect -r 0

Reference about these displays: 

- http://www.instructables.com/id/Using-PCF8574-backpacks-with-LCD-modules-and-Ardui/
- https://tronixlabs.com.au/display/lcd/serial-i2c-backpack-for-hd44780-compatible-lcd-modules-australia/

----

An open-source audio sampler project based on RaspberryPi.

Website: www.samplerbox.org

[![](http://gget.it/flurexml/1.jpg)](https://www.youtube.com/watch?v=yz7GZ8YOjTw)

[Install](#install)
----

SamplerBox works with the RaspberryPi's built-in soundcard, but it is recommended to use a USB DAC (such as [this 6€ one](http://www.ebay.fr/itm/1Pc-PCM2704-5V-Mini-USB-Alimente-Sound-Carte-DAC-decodeur-Board-pr-ordinateur-PC-/231334667385?pt=LH_DefaultDomain_71&hash=item35dc9ee479)) for better sound quality.

1. Install the required dependencies (Python-related packages and audio libraries):

  ~~~
  sudo apt-get update ; sudo apt-get -y install git python-dev python-pip python-numpy cython python-smbus portaudio19-dev libportaudio2 libffi-dev
  sudo pip install rtmidi-python pyaudio cffi sounddevice
  ~~~

2. Download SamplerBox and build it with: 

  ~~~
  git clone https://github.com/josephernest/SamplerBox.git
  cd SamplerBox ; sudo python setup.py build_ext --inplace
  ~~~

3. Run the soft with `python samplerbox.py`.

4. Play some notes on the connected MIDI keyboard, you'll hear some sound!  

*(Optional)*  Modify `samplerbox.py`'s first lines if you want to change root directory for sample-sets, default soundcard, etc.


[How to use it](#howto)
----

See the [FAQ](http://www.samplerbox.org/faq) on www.samplerbox.org.


[ISO image](#isoimage)
----

The ready-to-use ISO images available on [www.samplerbox.org](http://www.samplerbox.org) are built with the help of a script that can be found in `isoimage/samplerbox_iso_maker.sh`.


[About](#about)
----

Author : Joseph Ernest (twitter: [@JosephErnest](http:/twitter.com/JosephErnest), mail: [contact@samplerbox.org](mailto:contact@samplerbox.org))


[License](#license)
----

[Creative Commons BY-SA 3.0](http://creativecommons.org/licenses/by-sa/3.0/)