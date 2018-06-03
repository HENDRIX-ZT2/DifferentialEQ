# take FFT over section of file
# average into one FFT per file
# difference to reference
# average of differences

import numpy as np
import soundfile as sf
import fourier
import xml.etree.ElementTree as ET
import os
import sys
from PyQt5 import QtWidgets, QtGui, QtCore
from matplotlib.backends.backend_qt4agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt4agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import matplotlib.pyplot as plt

def showdialog(str):
	msg = QtWidgets.QMessageBox()
	msg.setIcon(QtWidgets.QMessageBox.Information)
	msg.setText(str)
	#msg.setInformativeText("This is additional information")
	msg.setWindowTitle("Error")
	#msg.setDetailedText("The details are as follows:")
	msg.setStandardButtons(QtWidgets.QMessageBox.Ok)
	retval = msg.exec_()
   
def spectrum_from_audio(filename, fft_size=4096, hop=256, channel_mode="L", start=None, end=None):
	print("reading",filename)
	soundob = sf.SoundFile(filename)
	sig = soundob.read(always_2d=True)
	sr = soundob.samplerate
	num_channels = sig.shape[1]
	spectra = []
	channels = {"L":(0,), "R":(1,), "L+R":(0,1)}
	for channel in channels[channel_mode]:
		print("channel",channel)
		if channel == num_channels:
			print("not enough channels for L/R comparison  - fallback to mono")
			break
		signal = sig[:,channel]
		
		#get the magnitude spectrum
		#avoid divide by 0 error in log
		imdata = 20 * np.log10(np.abs(fourier.stft(signal, fft_size, hop, "hann")+.0000001))
		spec = np.mean(imdata, axis=1)
		spectra.append(spec)
	#pad the data so we can compare this in a stereo setting if required
	if len(spectra) < 2:
		spectra.append(spectra[0])
	# return np.mean(spectra, axis=0), sr
	return spectra, sr

def indent(e, level=0):
	i = "\n" + level*"	"
	if len(e):
		if not e.text or not e.text.strip(): e.text = i + "	"
		if not e.tail or not e.tail.strip(): e.tail = i
		for e in e: indent(e, level+1)
		if not e.tail or not e.tail.strip(): e.tail = i
	else:
		if level and (not e.tail or not e.tail.strip()): e.tail = i
		
def write_eq(file_path, freqs, dB):
		tree=ET.ElementTree()
		equalizationeffect = ET.Element('equalizationeffect')
		curve=ET.SubElement(equalizationeffect, 'curve')
		curve.attrib["name"] = os.path.basename(file_path)[:-4]
		for f,d in zip(freqs,dB):
			point=ET.SubElement(curve, 'point')
			point.attrib["f"] = str(f)
			point.attrib["d"] = str(d)
		tree._setroot(equalizationeffect)
		indent(equalizationeffect)
		tree.write(file_path)
		
def get_eq(file_src, file_ref, channel_mode):
	print("Comparing channels:",channel_mode)
	#get the averaged spectrum for this audio file
	fft_size=16384
	hop=8192
	#todo: set custom times for both, if given
	spectra_src, sr_src = spectrum_from_audio(file_src, fft_size, hop, channel_mode)
	spectra_ref, sr_ref = spectrum_from_audio(file_ref, fft_size, hop, channel_mode)

	freqs = fourier.fft_freqs(fft_size, sr_src)
	#resample the ref spectrum to match the source
	if sr_src != sr_ref:
		spectra_ref = np.interp(freqs, fourier.fft_freqs(fft_size, sr_ref), spectra_ref)
	return freqs, np.asarray(spectra_ref)-np.asarray(spectra_src)
	

def moving_average(a, n=3) :
	ret = np.cumsum(a, dtype=float)
	ret[n:] = ret[n:] - ret[:-n]
	return ret[n - 1:] / n
	
class Window(QtWidgets.QMainWindow):
	def __init__(self, parent=None):
		super(Window, self).__init__(parent)
		
		self.central_widget = QtWidgets.QWidget(self)
		self.setCentralWidget(self.central_widget)
		
		self.setWindowTitle('Differential EQ')
		self.src_dir = "C:\\"
		self.ref_dir = "C:\\"
		self.out_dir = "C:\\"
		self.names = []
		self.freqs = []
		self.eqs = []
		self.av = []
		self.freqs_av = []

		# a figure instance to plot on
		self.figure = Figure()
		# create an axis
		self.ax = self.figure.add_subplot(111)

		# this is the Canvas Widget that displays the `figure`
		# it takes the `figure` instance as a parameter to __init__
		self.canvas = FigureCanvas(self.figure)

		# this is the Navigation widget
		# it takes the Canvas widget and a parent
		self.toolbar = NavigationToolbar(self.canvas, self)

		# Just some button connected to `plot` method
		self.b_add = QtWidgets.QPushButton('+')
		self.b_add.setToolTip("Add a source - reference pair to the list.")
		self.b_add.clicked.connect(self.add)
		self.b_delete = QtWidgets.QPushButton('-')
		self.b_delete.setToolTip("Delete the selected source - reference pair from the list.")
		self.b_delete.clicked.connect(self.delete)
		self.b_save = QtWidgets.QPushButton('=')
		self.b_save.setToolTip("Write the average EQ curve to an XML file.")
		self.b_save.clicked.connect(self.write)
		self.sp_a = QtWidgets.QSpinBox()
		self.sp_a.valueChanged.connect(self.plot)
		self.sp_a.setRange(0, 22000)
		self.sp_a.setSingleStep(1000)
		self.sp_a.setValue(21000)
		self.sp_a.setToolTip("At this frequency, the EQ still has full influence.")
		self.sp_b = QtWidgets.QSpinBox()
		self.sp_b.valueChanged.connect(self.plot)
		self.sp_b.setRange(0, 22000)
		self.sp_b.setSingleStep(1000)
		self.sp_b.setValue(22000)
		self.sp_b.setToolTip("At this frequency, the effect of the EQ becomes zero.")
		self.c_channels = QtWidgets.QComboBox(self)
		self.c_channels.addItems(list(("L+R","L","R")))
		self.c_channels.setToolTip("Which channels should be analyzed?")
		self.out_p = QtWidgets.QSpinBox()
		self.out_p.valueChanged.connect(self.plot)
		self.out_p.setRange(20, 2000)
		self.out_p.setSingleStep(100)
		self.out_p.setValue(200)
		self.out_p.setToolTip("Resolution of the output curve.")
		self.smooth_p = QtWidgets.QSpinBox()
		self.smooth_p.valueChanged.connect(self.plot)
		self.smooth_p.setRange(1, 200)
		self.smooth_p.setSingleStep(10)
		self.smooth_p.setValue(50)
		self.smooth_p.setToolTip("Smoothing factor. Hint: Increase this if your sample size is small.")

		self.listWidget = QtWidgets.QListWidget()
		
		self.qgrid = QtWidgets.QGridLayout()
		self.qgrid.setHorizontalSpacing(0)
		self.qgrid.setVerticalSpacing(0)
		self.qgrid.addWidget(self.toolbar, 0, 0, 1, 2)
		self.qgrid.addWidget(self.canvas, 1, 0, 1, 2)
		self.qgrid.addWidget(self.listWidget, 2, 0, 8, 1)
		self.qgrid.addWidget(self.b_add, 2, 1)
		self.qgrid.addWidget(self.b_delete, 3, 1)
		self.qgrid.addWidget(self.b_save, 4, 1)
		self.qgrid.addWidget(self.sp_a, 5, 1)
		self.qgrid.addWidget(self.sp_b, 6, 1)
		self.qgrid.addWidget(self.c_channels, 7, 1)
		self.qgrid.addWidget(self.out_p, 8, 1)
		self.qgrid.addWidget(self.smooth_p, 9, 1)
		
		self.colors = plt.rcParams['axes.prop_cycle'].by_key()['color']
		self.central_widget.setLayout(self.qgrid)
		
		
	def add(self):
		file_src = QtWidgets.QFileDialog.getOpenFileName(self, 'Open Source', self.src_dir, "Audio files (*.flac *.wav *.ogg *.aiff)")[0]
		if file_src:
			self.src_dir, src_name = os.path.split(file_src)
			file_ref = QtWidgets.QFileDialog.getOpenFileName(self, 'Open Reference', self.ref_dir, "Audio files (*.flac *.wav *.ogg *.aiff)")[0]
			if file_ref:
				channel_mode = self.c_channels.currentText()
				self.ref_dir, ref_name = os.path.split(file_ref)
				eq_name = src_name +" ("+channel_mode+") -> " + ref_name+" ("+channel_mode+")"
				self.freqs, eq = get_eq(file_src, file_ref, channel_mode)
				self.listWidget.addItem(eq_name)
				self.names.append(eq_name)
				self.eqs.append( eq )
				self.update_color(eq_name)
				self.plot()
			
	def update_color(self, eq_name):
		item = self.listWidget.findItems(eq_name, QtCore.Qt.MatchFixedString)[-1]
		#don't include the first (blue) -> reserved for the bold line
		item.setForeground( QtGui.QColor(self.colors[self.names.index(eq_name)+1]) )
		
	def delete(self):
		for item in self.listWidget.selectedItems():
			for i in reversed(range(0, len(self.names))):
				if self.names[i] == item.text():
					self.names.pop(i)
					self.eqs.pop(i)
			self.listWidget.takeItem(self.listWidget.row(item))
		
		for eq_name in self.names:
			self.update_color(eq_name)
		self.plot()
		
	def write(self):
		file_out = QtWidgets.QFileDialog.getSaveFileName(self, 'Save Average EQ', self.out_dir, "XML files (*.xml)")[0]
		file_base = ".".join(file_out.split(".")[:-1])
		if file_out:
			try:
				self.out_dir, eq_name = os.path.split(file_out)
				write_eq(file_base+"_AV.xml", self.freqs_av, np.mean(self.av, axis=0))
				write_eq(file_base+"_L.xml", self.freqs_av, self.av[0])
				write_eq(file_base+"_R.xml", self.freqs_av, self.av[1])
			except PermissionError:
				showdialog("Could not write files - do you have writing permissions there?")
	
	def plot(self):

		# discards the old graph
		self.ax.clear()
		if self.names:
			num_in = 2000
			#average over n samples, then reduce the step according to the desired output
			n = self.smooth_p.value()
			num_out = self.out_p.value()
			reduction_step = num_in // num_out
			#take the average curve of all differential EQs
			av_in = np.mean( np.asarray(self.eqs), axis=0)
			rolloff_start = self.sp_a.value()
			rolloff_end = self.sp_b.value()
			
			#audacity EQ starts at 20Hz
			freqs_spaced = np.power(2, np.linspace(np.log2(20), np.log2(self.freqs[-1]), num=num_in))
			
			avs = []
			#smoothen the curves, and reduce the points with step indexing
			self.freqs_av = moving_average(freqs_spaced, n=n)[::reduction_step]
			for channel in (0,1):
				#interpolate this channel's EQ, then smoothen and reduce keys for this channel
				avs.append( moving_average(np.interp(freqs_spaced, self.freqs, av_in[channel]), n=n)[::reduction_step] )
			self.av = np.asarray(avs)
			
			#get the gain of the filtered  EQ
			if rolloff_end:
				idx1 = np.abs(self.freqs_av-70).argmin()
				idx2 = np.abs(self.freqs_av-rolloff_end).argmin()
				gain = np.mean(self.av[:,idx1:idx2])
			else:
				gain = np.mean(self.av)
			self.av -= gain
			
			#fade out?
			if rolloff_start and rolloff_end:
				for channel in (0,1):
					self.av[channel] *= np.interp(self.freqs_av, (rolloff_start, rolloff_end), (1, 0) )
				
			#take the average
			self.ax.semilogx(self.freqs_av, np.mean(self.av, axis=0), basex=2, linewidth=2.5)
			
			#again, just show from 20Hz
			from20Hz = (np.abs(self.freqs-20)).argmin()
			#plot the contributing raw curves
			for name, eq in zip(self.names, np.mean(np.asarray(self.eqs), axis=1)):
				self.ax.semilogx(self.freqs[from20Hz:], eq[from20Hz:], basex=2, linestyle="dashed", linewidth=.5)
		# refresh canvas
		self.canvas.draw()

if __name__ == '__main__':
	app = QtWidgets.QApplication(sys.argv)

	main = Window()
	main.show()

	sys.exit(app.exec_())