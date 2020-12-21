'''



'''
import sys
sys.path.append("/home/regotlab/Documents/ImageAnalysisPython/")

from src.preprocessImages import *


inputStruct = {}
inputStruct['inputParentPath'] = '/media/sf_LocalAnalysisY/Helen/203010_HATiBrafV600E/RawImages'
inputStruct['outputParentPath'] = '/media/sf_LocalAnalysisY/Helen/203010_HATiBrafV600E/Images'
# if empty, all subfolders in the inputPath will be preprocessed
inputStruct['subfolderNames'] = [] 

# these must exactly match the channel names in micro-manager. 
#the first channel will be used for stitching (if applicable) and for image registration.
inputStruct['channels'] = ['Far-red','DAPI','CFP'] 

inputStruct['applyFlatFielding'] = True
inputStruct['prefix'] = 'Pos'
inputStruct['UseSingleFrame'] =False
#If UseSingleFrame == False, then define the start position and end position
inputStruct['startFlatfieldPos'] = 60
inputStruct['endFlatfieldPos'] = 62



inputStruct['applyImageRegistration'] = False

# if processFrames is empty, all frames will be processed.
# if processFrames has values greater than or equal to zero, only those frames will be processed.
# if processFrames has values less than zero, those frames will be ignored.
inputStruct['processFrames'] = []

#TRUE if no print statement
inputStruct['quite'] = False

#number of CPUs; 0 will consider all CPUs
inputStruct['CPU_NUMs'] = 0

#### call the mother function
preprocessImagesCaller(inputStruct)
