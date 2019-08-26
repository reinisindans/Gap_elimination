import arcpy
import os
from itertools import takewhile
from scipy.spatial import Delaunay
import numpy as np
import matplotlib.pyplot as plt

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

def createDelaunay(polygons):
    print "continuing..."
    # Best practice would be to implement the (slightly) modified delaunay triangulation here, instead of using the ready-made ArcMap functionality
    # Right now I use the Delaunay class from scypa.spatial library. The extra lines are then being tested if the Lines are correctly placed and the wrong ones are deleted. 
    for polygon in polygons:
        print "New Gap Polygon!!!"
        print "Trying to convert to np.array()"
        numpyPolygon=np.array(polygon)
        print numpyPolygon
        print "\n performing delaunay"
        delaunayTriangulation=Delaunay(numpyPolygon[:,1:], qhull_options='Qbb Qx Qs QJ Qz Qt Q12')
        print ("Delaunay simplices: ", delaunayTriangulation.simplices)
        print ("Delaunay coordinates: ")
        print numpyPolygon[:,1:]
        plt.triplot(numpyPolygon[:,1], numpyPolygon[:,2], delaunayTriangulation.simplices)
        plt.plot(numpyPolygon[:,1], numpyPolygon[:,2], 'o')
        for vertice in polygon:
            nr=vertice[0]
            x=vertice[1]
            y=vertice[2]
            print nr,x,y
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
createDelaunay(polygons)
