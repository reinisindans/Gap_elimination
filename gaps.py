import arcpy
import os
from itertools import takewhile
from scipy.spatial import Delaunay
import numpy as np
import matplotlib.pyplot as plt
import shutil # for deleting temp files, folders
import math

def createSubdir(workspace, subdirList):
    for subdir in subdirList:
        if not os.path.isdir(workspace + '/' + subdir):
            print ("Creating dirs"+ subdir)
            os.mkdir(workspace + '/' + subdir)

def searchSHP(workspace):
    try:
        fileCounter=0
        for file in os.listdir(workspace):
            if file.endswith(".shp"):
                fileCounter+=1
                shapefile=os.path.join(workspace, file)
                print shapefile
                return shapefile
                break
        if (fileCounter>1):
            sys.exit("There are more than 1 shapefiles in the working Folder!!")
        if (fileCounter<1):
            sys.exit("There are NO shapefiles in the working Folder!!")
    except:
        print("Something is wrong with the shapefile! Are You sure exactly one shapefile exists in the directory with the python script?")

def getHoles(input_fc):
    with arcpy.da.UpdateCursor(input_fc, "SHAPE@") as cur:
        for polygon, in cur:
            if polygon is None: continue
            SR = polygon.spatialReference
            polygon = arcpy.Polygon(
                arcpy.Array(
                    (pt for pt in takewhile(bool, part))
                    for part
                    in polygon.getPart() or arcpy.Array(arcpy.Array())
                ), SR
            )
            print "Updating...."
            cur.updateRow([polygon])

def extractPolygons(singleparts):
    polygons=[]
    with arcpy.da.SearchCursor(singleparts,['OID@','SHAPE@']) as cursor:
        for row in cursor:
            array1=row[1].getPart()
            polygon=[]
            for vertice in range(row[1].pointCount):
                pnt=array1.getObject(0).getObject(vertice)
                polygon.append([row[0],pnt.X,pnt.Y])
            polygons.append(polygon)
    return polygons

def isBetweenAngles(compareAngle, startStopAngles):
    answer = False 
    angle1= startStopAngles[0]
    angle2= startStopAngles[1]
    #Subtract start angle from all angles
    compareAngle -= angle1
    angle2 -= angle1
    angle1 -= angle1
    angles=[compareAngle, angle1, angle2]
    # if any angles are negative, add 360 to them!
    for angle in angles:
        if angle < 0:
            angle +=2*math.pi
    if angles[0] < angles[2]:
        answer= True
    return answer

def getAngle(points):
    point1= points[0]
    point2= points[1]
    angle= math.atan2(point2[1]-point1[1],point2[0]- point1[0])
    return angle
    
def getAllowedAngleSpan(points):
    point1= points[0]
    point2= points[1]
    point3= points[2]
    angle1= getAngle([point1,point2])
    #print "Angle1: ", math.degrees(angle1)
    angle2= getAngle([point1,point3])
    #print "Angle2: ",math.degrees(angle2)
    return [angle1,angle2]


def createDelaunay(output_fc, polygons):
    print "continuing..."
    # Best practice would be to implement the (slightly) modified delaunay triangulation here, instead of using the ready-made ArcMap functionality
    # Right now I use the Delaunay class from scipy.spatial library. The extra lines are then being tested if the Lines are correctly placed and the wrong ones are deleted. 
    for polygon in polygons:
        allowedAnglesFromPoint=[]
        print "New Gap Polygon!!!"
        numpyPolygon=np.array(polygon)
        print numpyPolygon
        delaunayTriangulation=Delaunay(numpyPolygon[:,1:], qhull_options='QbB Qx Qs Qz Qt Q12')
        print ("Delaunay simplices: ", delaunayTriangulation.simplices)
            
        allowedAngleSpan=[]
        for i in range(numpyPolygon.shape[0]-1):
            print "Point ", i
            if i==0:
                point1=numpyPolygon[0,1:]
                point2=numpyPolygon[-2,1:]
                point3=numpyPolygon[1,1:]
                print ("First Points: "+ str(numpyPolygon[0,0])+ " and "+ str(numpyPolygon[-2,0])+ " and "+ str(numpyPolygon[1,0]))
                points=[point1,point2,point3]
                print "First point"
                allowedAngleSpan.append(getAllowedAngleSpan(points))
            elif i==numpyPolygon.shape[0]-2:
                point1=numpyPolygon[i,1:]
                point2=numpyPolygon[i-1,1:]
                point3=numpyPolygon[0,1:]
                points=[point1,point2,point3]
                print "last point"
                allowedAngleSpan.append(getAllowedAngleSpan(points))
            else:
                point1=numpyPolygon[i,1:]
                point2=numpyPolygon[i-1,1:]
                point3=numpyPolygon[i+1,1:]
                points=[point1,point2,point3]
                print "normal point"
                allowedAngleSpan.append(getAllowedAngleSpan(points))
        print allowedAngleSpan        
        # checking if delaunay points are ok
        newSimpliceArray=[]
        for simplice in delaunayTriangulation.simplices:
            point1=numpyPolygon[simplice[0],1:]
            point2=numpyPolygon[simplice[1],1:]
            point3=numpyPolygon[simplice[2],1:]
            compareTo=allowedAngleSpan[simplice[0]]
            points= [point1,point2,point3]
            angle= getAngle(points)
            print ("Simplice:" + str(simplice) +" Angle: "+ str(math.degrees(angle))+ "  Must be between "+ str(math.degrees(compareTo[0]))+ "  and "+ str(math.degrees(compareTo[1])))
            print "Is between angles? ----> ", str(isBetweenAngles(angle,compareTo))
            if isBetweenAngles(angle,compareTo):
                newSimpliceArray.append(simplice)
        delaunayTriangulation.simplices=np.array(newSimpliceArray)
        print delaunayTriangulation.simplices
        #add to Triangulation shapefile! 
        # Plotting just for visualization
        plt.triplot(numpyPolygon[:,1], numpyPolygon[:,2], delaunayTriangulation.simplices)
        for i in range(len(polygon)-1):
            plt.text(polygon[i][1], polygon[i][2], i, va="top", family="monospace")
            
        plt.plot(numpyPolygon[:-1,1], numpyPolygon[:-1,2], 'o')
    plt.show()
        

# MAIN
arcpy.env.overwriteOutput = True
workspace = os.path.dirname(os.path.realpath(__file__))
temp_folder= "Temp"
temp_path=workspace+"/"+temp_folder
output_folder= "Output"
output_path= workspace+"/"+output_folder
createSubdir(workspace, [temp_folder, output_folder])
input_shapefile=searchSHP(workspace)
dissolved=temp_path+"/dissolved.shp"
holes=temp_path+"/holes.shp"
singleparts=temp_path+"/singleparts.shp"
triangles=temp_path+"/triangles.shp"

# Find gaps in polygon layer 1) union 2) fill Gaps 3) Difference

arcpy.Dissolve_management (input_shapefile, dissolved)
getHoles(dissolved)
#arcpy.FillGaps_production (dissolved, 0.0 )
arcpy.Erase_analysis(dissolved, input_shapefile, holes)
#arcpy.Delete_management(singleparts)
arcpy.MultipartToSinglepart_management (holes, singleparts)

#Create delaunay Triangulation, get middle of Delaunay lines 1) get middle of
# Delaunay lines 2) create triangle-Polygons using the Vertices of Polygon and
# Delaunay line middle points
polygons=extractPolygons(singleparts)
createDelaunay(triangles, polygons)



shutil.rmtree(temp_path)
