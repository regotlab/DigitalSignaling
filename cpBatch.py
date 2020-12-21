#!/usr/bin/python

import sys
import os
import subprocess
import re
import glob
import multiprocessing
import json
import shutil
import Image
import math
import functools
from datetime import datetime

strFormat = '%Y-%m-%d %H:%M:%S'
filenameStrFormat = '%Y-%m-%d-%H%M%S'
startTime = datetime.now()

# start parallelization functions
def feedFunc(queue, argsList):
	for args in argsList:
		queue.put(args)


def analyzeImageDirCpWrap(queueIn, queueOut):
	while True:
		try:
			args = queueIn.get(block=False)
			subfolder = args[0]

			queueOut.put(datetime.now().strftime(strFormat) + ' starting ' + subfolder + '\n')

			outputStr = analyzeImageDirCp(*args[1:])

			queueOut.put(outputStr)
		except:
			break


def writeFunc(queue, fpath):
	fhandle = open(fpath, 'a')
	while True:
		try:
			fhandle.write(queue.get(block=False))
			fhandle.flush()
		except:
			break
	fhandle.close()
# end parallelization functions


def analyzeParentDirCp(pipelineFilepath, inputParentPath, outputParentPath, outputFilename='cpData.mat', subfolderNames=[],
	frameFirstLast=[], cellProfilerPath='', preClean=True, runCellProfiler=True, runChannelImageCompression=True, nMaxCores=0):

	# check the inputs
	if not os.path.isfile(pipelineFilepath):
		raise Exception('Supplied pipelineFilepath does not exist')

	if not os.path.isdir(inputParentPath):
		raise Exception('Supplied inputParentPath does not exist')

	if inputParentPath==outputParentPath:
		raise Exception('inputParentPath and outputParentPath are the same')

	if not which('mogrify'):
		raise Exception('ImageMagick is not available from the command line')

	if len(frameFirstLast)!=0 and len(frameFirstLast)!=2:
		raise Exception('frameFirstLast must be empty or have length 2')

	if frameFirstLast:
		if not all((isinstance(frame, (int, long)) for frame in frameFirstLast)):
			raise Exception('Frame numbers must be integers')

		if any((frame<0 for frame in frameFirstLast)):
			raise Exception('Frame numbers must be greater than or equal to zero')

		if frameFirstLast[0]>frameFirstLast[1]:
			raise Exception('Last frame must be greater than or equal to first frame')

	if not os.path.isdir(outputParentPath):
		os.makedirs(outputParentPath)

	# save the inputs
	inputArgsFilename = 'cpBatchArgs_' + startTime.strftime(filenameStrFormat) + '.json'
	inputArgs = locals()
	inputArgsJson = json.dumps(inputArgs)
	inputArgsFile = open(os.path.join(outputParentPath, inputArgsFilename), 'w')
	inputArgsFile.write(inputArgsJson + '\n')
	inputArgsFile.close()

	if runCellProfiler:
		# get cellprofiler path
		if not cellProfilerPath:
			cellProfilerPath = getCellProfilerPath()
		else:
			cellProfilerPath = raw(cellProfilerPath)

	# check the subfolders
	if len(subfolderNames)==0:
		subfolderNamesExist = [dirName for dirName in os.listdir(inputParentPath) if os.path.isdir(os.path.join(inputParentPath, dirName))]
	else:
		subfolderNamesExist = [dirName for dirName in subfolderNames if os.path.isdir(os.path.join(inputParentPath, dirName))]

		setNamesInput = set(subfolderNames)

		diffSetList = list(setNamesInput.difference(set(subfolderNamesExist)))
		if len(diffSetList)>0:
			f.write(datetime.now().strftime(strFormat) + ' ' + ', '.join(diffSetList) + \
			' subfolder(s) do(es) not exist and will be ignored\n')

	# initialize the log file
	logFilename = 'cpBatch_' + startTime.strftime(filenameStrFormat) + '.log'
	logFilepath = os.path.join(outputParentPath, logFilename)
	f = open(logFilepath, 'w')
	f.write(startTime.strftime(strFormat) + ' starting analysis\n')
	f.write(startTime.strftime(strFormat) + ' number of subfolders to analyze: ' + str(len(subfolderNamesExist)) + '\n')
	f.close()

	########## start of parallelization
	argsList = []
	for subfolder in subfolderNamesExist:
		inputPath = os.path.join(inputParentPath, subfolder)
		outputPath = os.path.join(outputParentPath, subfolder)
		argsList = argsList + [(subfolder, pipelineFilepath, inputPath, outputPath, outputFilename, frameFirstLast,
			cellProfilerPath, preClean, runCellProfiler, runChannelImageCompression)]

	n = min([int(x) for x in [nMaxCores, multiprocessing.cpu_count()] if int(x)>0])

	workerQueue = multiprocessing.Queue()
	writerQueue = multiprocessing.Queue()

	feedProc = multiprocessing.Process(target=feedFunc, args=(workerQueue, argsList))
	analyzeProc = [multiprocessing.Process(target=analyzeImageDirCpWrap, args=(workerQueue, writerQueue)) for ii in range(n)]
	writeProc = multiprocessing.Process(target=writeFunc, args=(writerQueue, logFilepath))

	feedProc.start()
	feedProc.join()
	for p in analyzeProc:
		p.start()
	for p in analyzeProc:
		p.join()
	writeProc.start()
	writeProc.join()
	########## end of parallelization

	# finish up the log file
	f = open(logFilepath, 'a')
	f.write(datetime.now().strftime(strFormat) + ' completed analysis of all folders\n')
	f.close()


def analyzeImageDirCp(pipelineFilepath, inputPath, outputPath, outputFilename, frameFirstLastInput=[],
	cellProfilerPath='', preClean=True, runCellProfiler=True, runChannelImageCompression=True):

	if runCellProfiler:
		if not cellProfilerPath:
			cellProfilerPath = getCellProfilerPath()
		else:
			cellProfilerPath = raw(cellProfilerPath)

	if not os.path.isdir(outputPath):
		os.makedirs(outputPath)
	elif preClean:
		shutil.rmtree(outputPath)
		os.makedirs(outputPath)

	# initialize the log file
	logFilename = 'cpBatch_' + startTime.strftime(filenameStrFormat) + '_' + os.path.split(inputPath)[1] + '.log'
	logFilepath = os.path.join(outputPath, logFilename)
	appendLogFile(logFilepath, 'starting analysis of ' + os.path.split(inputPath)[1])
	appendLogFile(logFilepath, 'preparing the output folder')

	appendLogFile(logFilepath, 'obtaining the frames and filenames')
	frameNumbers, imageFilenames = getFrameData(inputPath)
	frameFirstLastIdx = getFrameFirstLastIdx(frameFirstLastInput, frameNumbers)

	if not frameFirstLastIdx:
		logStringFull = appendLogFile(logFilepath, os.path.split(inputPath)[1] + ' has no frames within frameFirstLast')
		return logStringFull

	if runCellProfiler:
		# copy pre-existing mat files not named outputFilename to outputPath
		appendLogFile(logFilepath, 'copying mat files fron input folder')
		copySomeFiles(os.path.join(inputPath, '*.mat'), outputPath, [outputFilename])

		fnull = open(os.devnull, 'w')

		# generate the list of strings with which to call cellprofiler (add one)
		cpCommand = [cellProfilerPath, '-c', '-r', '-p', pipelineFilepath, '-i', inputPath,
			'-o', outputPath, os.path.join(outputPath, outputFilename),
			'-f', str(frameFirstLastIdx[0]+1), '-l', str(frameFirstLastIdx[1]+1)]

		# run cellprofiler
		verifiedComplete = False
		nMaxAttempts = 3
		nFails = 0
		while not verifiedComplete and nFails < nMaxAttempts:
			appendLogFile(logFilepath, 'running the CellProfiler pipeline')
			if os.name == 'nt':
				subprocess.call(cpCommand, stdout=fnull, stderr=fnull)
			elif os.name == 'posix':
				subprocess.call(['python'] + cpCommand, stdout=fnull, stderr=fnull)
				
			if os.path.isfile(os.path.join(outputPath, outputFilename)):
				verifiedComplete = True
				
				appendLogFile(logFilepath, 'converting object images from tiff to png')
				convertTif2Png(outputPath, os.path.join(outputPath, 'objects'))
				
				appendLogFile(logFilepath, 'creating object outline images')
				makeObjectOutlines(os.path.join(outputPath, 'objects'), os.path.join(outputPath, 'outlines'))
		
			else:
				appendLogFile(logFilepath, 'CellProfiler aborted for some reason')
				nFails = nFails + 1
				if nFails < nMaxAttempts:
					appendLogFile(logFilepath, 'cleaning out the outputPath in preparation for trying again')
				else:
					appendLogFile(logFilepath, 'cleaning out the outputPath and then giving up')
				(head, tail) = os.path.split(outputPath)
				tmpPath = os.path.join(head, tail + '-tmp')
				os.mkdir(tmpPath)
				shutil.move(logFilepath, tmpPath)
				shutil.rmtree(outputPath)
				os.mkdir(outputPath)
				shutil.move(os.path.join(tmpPath, logFilename), outputPath)
				shutil.rmtree(tmpPath)
				copySomeFiles(os.path.join(inputPath, '*.mat'), outputPath, [outputFilename])
				
	if runChannelImageCompression:
		appendLogFile(logFilepath, 'compressing channel images')
		compressChannelImages(inputPath, os.path.join(outputPath, 'channels'), imageFilenames, frameFirstLastIdx)

	# finish up
	logStringFull = appendLogFile(logFilepath, ''.join(['completed ', os.path.split(inputPath)[1], ' (frames ',
		str(frameNumbers[frameFirstLastIdx[0]]), ' through ', str(frameNumbers[frameFirstLastIdx[1]]), ')']))
	return logStringFull


def appendLogFile(filepath, logString):
	logStringFull = datetime.now().strftime(strFormat) + ' ' + logString + '\n'
	f = open(filepath, 'a')
	f.write(logStringFull)
	f.close()
	return logStringFull


def getCellProfilerPath():
	# probably can't handle mac
	if os.name == 'posix':
		cellProfilerPath = '/usr/local/CellProfiler/CellProfiler.py'
		if not os.path.isfile(cellProfilerPath):
			raise Exception('Please provide the path to CellProfiler.py in cpBatchArgs')

	elif os.name == 'nt':
		cellProfilerPath = which('CellProfiler')
		if not cellProfilerPath:
			cellProfilerPath = 'C:\\Program Files\\CellProfiler\\CellProfiler.exe' # note the direction of the slashes
			cellProfilerPath2 = 'C:\\Program Files (x86)\\CellProfiler\CellProfiler.exe'
			if not os.path.isfile(cellProfilerPath):
				if os.path.isfile(cellProfilerPath2):
					cellProfilerPath = cellProfilerPath2
				else:
					raise Exception('Please provide the path to CellProfiler.exe in cpBatchArgs')

	return cellProfilerPath


def copySomeFiles(inputPathWithGlobPattern, outputPath, excludeFileList=[]):
	filepaths = glob.glob(inputPathWithGlobPattern)
	filepaths = [filepath for filepath in filepaths if os.path.split(filepath)[1] not in excludeFileList]
	for filepath in filepaths:
		shutil.copy2(filepath, outputPath)


def getFrameData(inputPath):
	imgKey = 'img_' # image files start with this
	imgExt = '.png'

	imgNames = [filename for filename in os.listdir(inputPath)
		if os.path.isfile(os.path.join(inputPath, filename)) and re.match(imgKey, filename) and os.path.splitext(filename)[1]==imgExt]
	imgNames.sort()

	frameStringsAll = [filename.split('_')[1] for filename in imgNames]
	frameNumbersAll = [int(frameStr) for frameStr in frameStringsAll]
	frameNumbers = list(set(frameNumbersAll))
	frameNumbers.sort()

	channelNamesAll = [filename.split('_')[2] for filename in imgNames]
	channelNames = list(set(channelNamesAll))
	channelNames.sort()

	imageFilenames = [x[:] for x in [['']*len(frameNumbers)]*len(channelNames)]
	for ii,filename in enumerate(imgNames):
		frameIdx = frameNumbers.index(frameNumbersAll[ii])
		channelIdx = channelNames.index(channelNamesAll[ii])
		imageFilenames[channelIdx][frameIdx] = filename

	return (frameNumbers, imageFilenames)


def getFrameFirstLastIdx(frameFirstLastInput, frameNumbers):
	frameFirstLastIdx = [0, len(frameNumbers)-1]

	if not frameFirstLastInput:
		return frameFirstLastIdx

	elif frameFirstLastInput[0]<=frameNumbers[-1] and frameFirstLastInput[1]>=frameNumbers[0]:
		lowFramesIdx = [idx for (idx, frame) in enumerate(frameNumbers) if frame<=frameFirstLastInput[0]]
		if lowFramesIdx:
			frameFirstLastIdx[0] = lowFramesIdx[-1]

		highFramesIdx = [idx for (idx, frame) in enumerate(frameNumbers) if frame>=frameFirstLastInput[1]]
		if highFramesIdx:
			frameFirstLastIdx[1] = highFramesIdx[0]

		return frameFirstLastIdx

	else:
		return None


def convertTif2Png(inputPath, outputPath = None):
	if outputPath is None:
		outputPath = inputPath
	else:
		if not os.path.isdir(outputPath):
			os.makedirs(outputPath)
	
	outExt = 'png'
	# batch convert all tifs to png
	tifExt = ['.tif', '.tiff']
	tifExtTry = (ext for ext in tifExt if glob.glob(os.path.join(inputPath, '*' + ext)))
	for ext in tifExtTry:
		subprocess.call(['mogrify', '-path', outputPath, '-format', outExt, os.path.join(inputPath, '*' + ext)])

	# remove all tifs that have a corresponding png
	allFiles = (filename for filename in os.listdir(inputPath) if os.path.isfile(os.path.join(inputPath, filename)))
	if inputPath == outputPath:
		for nowFile in allFiles:
			filename, fileext = os.path.splitext(nowFile)
			if (fileext in tifExt) and os.path.isfile(os.path.join(outputPath, filename + '.' + outExt)):
				os.remove(os.path.join(inputPath, nowFile))
	else:
		for nowFile in allFiles:
			filename, fileext = os.path.splitext(nowFile)
			if fileext in tifExt:
				if os.path.isfile(os.path.join(outputPath, filename + '.' + outExt)):
					os.remove(os.path.join(inputPath, nowFile))
				else:
					shutil.move(os.path.join(inputPath, nowFile), outputPath)


def makeObjectOutlines(inputPath, outputPath = None):
	if outputPath is None:
		outputPath = os.path.join(inputPath, '..', 'tmpImages')
		inOutSame = True
	else:
		inOutSame = False

	imgMatch = '*.png'
	imgSuf = 'outlines.png'
	imgSufRe = '\.outlines\.png'
	sepNew = '_'
	kernel = 'square'

	if glob.glob(os.path.join(inputPath, imgMatch)):
		if not os.path.isdir(outputPath):
			os.makedirs(outputPath)

		# make the outlines images in a subfolder
		subprocess.call(['mogrify', '-path', outputPath, '-format', imgSuf,
			'-morphology', 'edgein', kernel, os.path.join(inputPath, imgMatch)])

		# change the . to _, and possibly move them into inputPath
		filesTmp = (filename for filename in os.listdir(outputPath) if re.search(imgSufRe, filename))
		if inOutSame:
			for filename in filesTmp:
				filenameNew = re.sub(imgSufRe, sepNew + imgSuf, filename)
				os.rename(os.path.join(outputPath, filename), os.path.join(inputPath, filenameNew))
			if not os.listdir(outputPath):
				os.rmdir(outputPath)
				
		else:
			for filename in filesTmp:
				filenameNew = re.sub(imgSufRe, sepNew + imgSuf, filename)
				os.rename(os.path.join(outputPath, filename), os.path.join(outputPath, filenameNew))


def scoreatpercentile(N, per, key=lambda x:x):
	"""
	Find the percentile of a list of values.

	@parameter N - is a list of values.
	@parameter per - a float value from 0 to 100.
	@parameter key - optional key function to compute value from each element of N.

	@return - the percentile of the values
	"""
	#import math
	#import functools
	if not N:
		return None
	frac = per / 100.0
	N.sort()
	k = (len(N)-1) * frac
	f = math.floor(k)
	c = math.ceil(k)
	if f == c:
		return key(N[int(k)])
	d0 = key(N[int(f)]) * (c-k)
	d1 = key(N[int(c)]) * (k-f)
	return d0+d1


def getLoHiForImages(inputPath, imageFilenames, percentiles):
	loHiAll = [[],[]]
	for filename in imageFilenames:
		img = Image.open(os.path.join(inputPath, filename))
		pixList = list(img.getdata())

		for ii in range(2):
			loHiAll[ii].append(scoreatpercentile(pixList, percentiles[ii]))

	loHiLevel = []
	loHiLevel.append(max(loHiAll[0]))
	loHiLevel.append(min(loHiAll[1]))

	if img.mode=='I':
		depth = 16
	else:
		depth = 8
	loHiPercent = [level / (2.0**depth-1) * 100 for level in loHiLevel]

	return loHiPercent


def compressChannelImages(inputPath, outputPath, imageFilenames, frameFirstLastIdx):
	# if compressing to 8-bit png, make sure to specify -depth 8
	percentiles = [1, 99.99] # from 0 to 100 (used for rescaling compressed images)
	sepChar = '_'
	outputExt = '.jpg'
	quality = 95
	
	if not os.path.isdir(outputPath):
		os.makedirs(outputPath)
		
	for channelFilenames in imageFilenames:
		compressFilenames = [filename for filename in channelFilenames[frameFirstLastIdx[0]:frameFirstLastIdx[1]+1] if filename]
		loHi = getLoHiForImages(inputPath, compressFilenames, percentiles)

		for filename in compressFilenames:
			subprocess.call(['convert', os.path.join(inputPath, filename), '-level', str(loHi[0])+'%,'+str(loHi[1])+'%',
				'-quality', str(quality), os.path.join(outputPath, os.path.splitext(filename)[0]+outputExt)])


def which(programIn):
	#import os
	def is_exe(fpath):
		return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

	# probably can't handle mac
	if os.name=='posix':
		program = programIn
	elif os.name=='nt':
		programRoot, programExt = os.path.splitext(programIn)
		if not programExt:
			program = programRoot + '.exe'
		else:
			program = programIn

	fpath, fname = os.path.split(program)
	if fpath:
		if is_exe(program):
			return program
	else:
		for path in os.environ["PATH"].split(os.pathsep):
			exe_file = os.path.join(path, program)
			if is_exe(exe_file):
				return exe_file

	return None


def raw(text):
	'''Returns a raw string representation of text'''
	escape_dict={'\a':r'\a', '\b':r'\b', '\c':r'\c', '\f':r'\f', '\n':r'\n', '\r':r'\r',
	'\t':r'\t', '\v':r'\v', '\'':r'\'', '\"':r'\"', '\0':r'\0', '\1':r'\1', '\2':r'\2',
	'\3':r'\3', '\4':r'\4', '\5':r'\5', '\6':r'\6', '\7':r'\7', '\8':r'\8', '\9':r'\9'}

	new_string=''
	for char in text:
		try: new_string+=escape_dict[char]
		except KeyError: new_string+=char
	return new_string


if __name__ == '__main__':
	cpArgs = __import__(os.path.splitext(sys.argv[1])[0])

	#inputArgNames = [item for item in cpArgs if not item.startswith("__")]
	#inputArgValues = [getattr(cpArgs, varname) for varname in inputVarNames]

	analyzeParentDirCp(cpArgs.pipelineFilepath, cpArgs.inputParentPath, cpArgs.outputParentPath,
		cpArgs.outputFilename, cpArgs.subfolderNames, cpArgs.frameFirstLast, cpArgs.cellProfilerPath,
		cpArgs.preClean, cpArgs.runCellProfiler, cpArgs.runChannelImageCompression, cpArgs.nMaxCores)

