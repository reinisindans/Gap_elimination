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
            cur.updateRow([polygon])

def extractPolygons(singleparts):
    polygons=[]
    with arcpy.da.SearchCursor(singleparts,['OID@','SHAPE@']) as cursor:
        for row in cursor:
            array1=row[1].getPart()
            polygon=[]
            verticeCount=0
            for vertice in range(row[1].pointCount):
                pnt=array1.getObject(0).getObject(vertice)
                polygon.append([row[0],pnt.X,pnt.Y])
                verticeCount+=1
            polygons.append(polygon)
    # Visualize
    plt.figure(1)
    for polygon in polygons:
        numpyPolygon=np.array(polygon)
        plt.plot(numpyPolygon[:,1], numpyPolygon[:,2], '-') 
        
    
    return polygons

def extractAllPoints(polygons, precision):
    # write new Geometries to dictionary -> dictionary provides efficient iteration while searching for geometries 
    point_dict={}
    for polygon in polygons:
        pointNr=0
        for point in polygon:
            # create a tuple from coordinates to use as key Schema: {geom=[OID, pntNr]}
            # Should be done more efficiently, in future implementation must be refactored
            # to get rid of this type change- and define the coordinates as tuple in the first case!
            geom=(round(point[1], precision),round(point[2],precision))
            point_dict[geom]= [point[0],pointNr]
            pointNr+= 1
    return point_dict

def comparePoints(point_dict, comparePoint):
    # !! comparePoint must be a coordinate tuple !! (X,Y)
    result= []
    if comparePoint in point_dict:
        result= point_dict[comparePoint]
    return result

def findPointId(pointXY, polygon, precision):
    pointID=0
    for point in polygon:
        if (round(pointXY[0],precision)==round(point[1], precision) and round(pointXY[1], precision)==round(point[2],precision)):
            break
        pointID+=1
    return pointID

def getMiddlePoint(points):
    point1_X= points[0][0]
    point1_Y= points[0][1]
    point2_X= points[1][0]
    point2_Y= points[1][1]
    middlePoint_X= (point1_X+point2_X)/2
    middlePoint_Y= (point2_Y+point2_Y)/2
    middlePoint=[middlePoint_X, middlePoint_Y]
    return middlePoint

def cut_geometry(to_cut, cutter):
    """
    Method copied from: https://gis.stackexchange.com/questions/124198/optimizing-arcpy-code-to-cut-polygon?noredirect=1&lq=1
    Author: Tristan Forward
    Cut a feature by a line, splitting it into its separate geometries.
    :param to_cut: The feature to cut.
    :param cutter: The polylines to cut the feature by.
    :return: The feature with the split geometry added to it.
    """
    arcpy.AddField_management(to_cut, "SOURCE_OID", "LONG")
    geometries = []
    polygon = None

    edit = arcpy.da.Editor(os.path.dirname(to_cut))
    edit.startEditing(False, False)

    insert_cursor = arcpy.da.InsertCursor(to_cut, ["SHAPE@", "SOURCE_OID"])

    with arcpy.da.SearchCursor(cutter, "SHAPE@") as lines:
        for line in lines:
            with arcpy.da.UpdateCursor(to_cut, ["SHAPE@", "OID@", "SOURCE_OID"]) as polygons:
                for polygon in polygons:
                    if line[0].disjoint(polygon[0]) == False:
                        if polygon[2] == None:
                            id = polygon[1]
                        # Remove previous geom if additional cuts are needed for intersecting lines
                        if len(geometries) > 1:
                            del geometries[0] 
                        geometries.append([polygon[0].cut(line[0]), id])
                        polygons.deleteRow()
                for geometryList in geometries:
                    for geometry in geometryList[0]:
                        if geometry.area > 0:
                            insert_cursor.insertRow([geometry, geometryList[1]])

    edit.stopEditing(True)

def createDelaunay(temp_path,triangles, polygons, SRS, polygon_nr, UID_field):
    # Creating the new Delaunay .shp
    output_fc= temp_path+"/"+triangles
    arcpy.CreateFeatureclass_management(temp_path, triangles, "POLYGON","" , "DISABLED", "DISABLED", SRS)
    arcpy.AddField_management(in_table=triangles_path, field_name=polygon_nr, field_type='LONG', field_length=10)
    arcpy.AddField_management(in_table=triangles_path, field_name=UID_field, field_type='LONG', field_length=10)

    # Best practice would be to implement the (slightly) modified delaunay triangulation here, instead of using the ready-made ArcMap functionality
    # Right now I use the Delaunay class from scipy.spatial library. The extra lines are then being tested if the Lines are correctly placed and the wrong ones are deleted. 
    uid=0
    for polygon in polygons:
        numpyPolygon=np.array(polygon)
        #print numpyPolygon
        delaunayTriangulation=Delaunay(numpyPolygon[:,1:], qhull_options='QbB Qx Qs Qz Qt Q12')

        #print ("Delaunay simplices: ", delaunayTriangulation.simplices)
        #print delaunayTriangulation.simplices
        #add to Triangulation shapefile!
        
        plt.figure(2)
        
        with arcpy.da.InsertCursor(output_fc,[UID_field,polygon_nr,'SHAPE@']) as cursor:
            for polygon in delaunayTriangulation.simplices:
                points=[]
                for point in polygon:
                    point= arcpy.Point(numpyPolygon[point,1],numpyPolygon[point,2])
                    points.append(point)
                array=arcpy.Array(points)
                polygon= arcpy.Polygon(array, SRS)
                cursor.insertRow([uid, numpyPolygon[0,0], polygon])
                uid+=1
                
            # Plotting just for visualization
            
            plt.triplot(numpyPolygon[:,1], numpyPolygon[:,2], delaunayTriangulation.simplices)
            plt.plot(numpyPolygon[:-1,1], numpyPolygon[:-1,2], 'o')
            for i in range(len(numpyPolygon)-1):
                plt.text(numpyPolygon[i][1], numpyPolygon[i][2], i, va="top", family="monospace")

def mergeFeatures(problem_points, featureClass, UID_field):
    for problem_point in problem_points.keys():
        rows_to_merge=[]
        fields= arcpy.ListFields(featureClass)
        field_names=[]
        desc=arcpy.Describe(featureClass)
        geometryType = desc.shapeType
        geometry_field_name=desc.ShapeFieldName
        for field in fields:
            field_names.append(field.name)
            
        field_names.pop(0) # remove the OID!!!! Otherwise it messes everythoing up by insert....0r no....
        geometry_index= field_names.index(geometry_field_name)
        UID_index= field_names.index(UID_field)
        field_names[geometry_index]='SHAPE@'  #Add extra geometry field because the field list does not really work!!!


        for UID in problem_points[problem_point]:
            sql=UID_field+"=%s" % (UID)
            with arcpy.da.UpdateCursor(featureClass,field_names,sql) as cursor:
                for row in cursor:
                        rows_to_merge.append(row)
                        cursor.deleteRow()
                        
        if len(rows_to_merge)>2:
            print "Too many polygons in problem point geometries!"

        new_polygons=[]
        while len(rows_to_merge)>1:
            rows_to_merge[-1][geometry_index]= rows_to_merge[-1][geometry_index].union(rows_to_merge[-2][geometry_index]) # taking all the field values except geometry from the last polygon!
            new_polygon=rows_to_merge[-1]
            new_polygon[geometry_index]= new_polygon[geometry_index].generalize(0) # remove the extra vertice
            new_polygons.append(new_polygon)

            rows_to_merge.pop() # removing the merged ones
            rows_to_merge.pop()
            pointArray=new_polygon[0].getPart()
            
        with arcpy.da.InsertCursor(featureClass,field_names) as cursor:
            for new_poly in new_polygons:                               
                cursor.insertRow(new_poly)
    return featureClass

def getProblemPoints(cutDelaunay_path, polygons, precision, UID_field):
    allPoints=extractAllPoints(polygons, precision)
    problem_points={} # points whose vertices do not coincide with gap polygon vertices. result of arcpy.Clip operation 
    with arcpy.da.SearchCursor(cutDelaunay_path, ["SHAPE@", UID_field]) as cursor:                          
                for row in cursor:
                    array=row[0].getPart()
                    for vertice in range(row[0].pointCount):
                        pnt=array.getObject(0).getObject(vertice)
                        geometry=(round(pnt.X,precision),round(pnt.Y,precision))
                        result= comparePoints(allPoints, geometry)
                        if result ==[]:  # Point is not one of the original Polygon Vertices!                            
                            if geometry in problem_points:
                                problem_set= problem_points[geometry]
                                problem_set.add(cursor[1])
                                problem_points[geometry]= problem_set # format: key: coordinates, value: IDs of Triangles                                
                            else:
                                problem_points[geometry]= {cursor[1]}                
        #check if any problem points only have one associated triangle triangle (Should not happen!!)
    for key in problem_points.keys():
        if len(problem_points[key])<2:            
            del problem_points[key]
    return problem_points

def eliminateFalseTriangles(cutDelaunay_path, polygons, precision, UID_field):
    problem_points=getProblemPoints(cutDelaunay_path, polygons, precision, UID_field) # points whose vertices do not coincide with gap polygon vertices. result of arcpy.Clip operation
    mergeFeatures(problem_points, cutDelaunay_path, UID_field)    
                    
def determineTriangleType(cutDelaunay_path, polygons, triangleType, precision, polygon_nr, UID_field):

    arcpy.AddField_management(cutDelaunay_path, triangleType, "SHORT")

    allPoints=extractAllPoints(polygons, precision)

    triangles=[]
    # Todo---> add while !isDoneFlag:  loop!
    with arcpy.da.UpdateCursor(cutDelaunay_path, ["SHAPE@", triangleType, polygon_nr, UID_field]) as cursor:        
        for row in cursor:
            # triangle type keys.   0 - error in determining the triangle type
            #                       1 - triangle is equal with original gap polygon
            #                       2 - triangle shares 2 sides with original gap poly, 1 extra point needed, plus the middle vertice
            #                       3 - tri shares 1 side w/ gap polygon, 2 extra points needed as middlepoints
            #                       4 - tri shares no sides w/ gap polygon, 3 middlepoints + centroid needed!
            geometry=row[0]
            if len(polygons[row[2]])==4: # Triangle equals original polygon - when Polygon is triangle itself
                row[1]=0
            else:
                array=geometry.getPart()
                pointIDs=[]

                for vertice in range(row[0].pointCount):
                    pnt=array.getObject(0).getObject(vertice)
                    pointXY=[pnt.X,pnt.Y]
                    pointId=findPointId(pointXY, polygons[row[2]], precision)
                    pointIDs.append(pointId)
                    
                    
                
                polygonString=""
                
                for i in range(len(polygons[row[2]])-2):
                    polygonString= polygonString+ str(i)
                polygonString= polygonString*2
                IDstring="".join(sorted(str(pointIDs[:-1])))
                IDstring = IDstring.translate(None, ',][ ')
                if (polygonString.find(IDstring)!=-1): # triangle shares 2 sides with original gap poly
                    row[1]=1
                    print ("1 !!!: "+ IDstring)
                    print ("POlyString: "+ polygonString)
                elif (polygonString.find(IDstring[:-1])!=-1 or polygonString.find(IDstring[1:])!=-1): #tri shares 1 side w/ gap polygon
                    row[1]=2
                    print ("2 !!!: "+ IDstring[:-1])
                    print ("POlyString: "+ polygonString)
                elif (polygonString.find(IDstring[:-2])!=-1):  #tri shares no sides w/ gap polygon
                    row[1]=3
                    #print ("3 !!!: "+ IDstring[:-2])
                else:
                    row[1]=-1
            cursor.updateRow(row)
            
    

# MAIN
arcpy.env.overwriteOutput = True
workspace = os.path.dirname(os.path.realpath(__file__))
temp_folder= "Temp"
temp_path=workspace+"/"+temp_folder
output_folder= "Output"
output_path= workspace+"/"+output_folder
createSubdir(workspace, [temp_folder, output_folder])
input_shapefile=searchSHP(workspace)
SRS= arcpy.Describe(input_shapefile).spatialReference
dissolved=temp_path+"/dissolved.shp"
holes=temp_path+"/holes.shp"
singleparts=temp_path+"/singleparts.shp"
triangles="triangles.shp"
triangles_path= temp_path+"/"+triangles
cutDelaunay_path=temp_path+"/cutDelaunay.shp"
triangleType="tri_type"
precision=4
UID_field="UID"
polygon_nr="PolyNo"

# Find gaps in polygon layer: 1) union 2) fill Gaps 3) Difference 4) To Singleparts
arcpy.Dissolve_management (input_shapefile, dissolved)
getHoles(dissolved)
arcpy.Erase_analysis(dissolved, input_shapefile, holes)
arcpy.MultipartToSinglepart_management (holes, singleparts)

#Create delaunay Triangulation, get middle of Delaunay lines 1) get middle of
# Delaunay lines 2) create triangle-Polygons using the Vertices of Polygon and
# Delaunay line middle points
polygons=extractPolygons(singleparts)

# creating the triangle shapefile
createDelaunay(temp_path,triangles, polygons, SRS, polygon_nr, UID_field)

#cut delauney with original holes to remove extras
arcpy.Clip_analysis(triangles_path, holes, cutDelaunay_path)

eliminateFalseTriangles(cutDelaunay_path, polygons, precision, UID_field)

determineTriangleType(cutDelaunay_path,polygons , triangleType, precision, polygon_nr, UID_field)

plt.show()

# Cut each Delaunay Polygon with the polygon centerlines
# cut_geometry(cutDelaunay_path, polygonCenterlines)

#shutil.rmtree(temp_path)
