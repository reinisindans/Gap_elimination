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
    # Getting the holes
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
    # getting hole polygons as a List of Coordinates
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
    middlePoint_Y= (point1_Y+point2_Y)/2
    middlePoint=[middlePoint_X, middlePoint_Y]
    return middlePoint

def getTriangleCentroid(points):
    point1_X= points[0][0]
    point1_Y= points[0][1]
    point2_X= points[1][0]
    point2_Y= points[1][1]
    point3_X= points[2][0]
    point3_Y= points[2][1]
    centroid_X= (point1_X+point2_X+point3_X)/3
    centroid_Y= (point1_Y+point2_Y+point3_Y)/3
    centroid=[centroid_X, centroid_Y]
    return centroid


def createDelaunay(temp_path,triangles, polygons, SRS, polygon_nr, UID_field, point_order , original_order):
    # Creating the new Delaunay .shp
    output_fc= temp_path+"/"+triangles
    arcpy.CreateFeatureclass_management(temp_path, triangles, "POLYGON","" , "DISABLED", "DISABLED", SRS)
    arcpy.AddField_management(in_table=triangles_path, field_name=polygon_nr, field_type='LONG', field_length=10)
    arcpy.AddField_management(in_table=triangles_path, field_name=UID_field, field_type='LONG', field_length=10)
    arcpy.AddField_management(in_table=triangles_path, field_name=point_order, field_type='TEXT', field_length=10)
    arcpy.AddField_management(in_table=triangles_path, field_name=original_order, field_type='TEXT', field_length=10)
    
    # Best practice would be to implement the (slightly) modified delaunay triangulation here, instead of using the ready-made ArcMap functionality
    # Right now I use the Delaunay class from scipy.spatial library. The extra lines are then being tested if the Lines are correctly placed and the wrong ones are deleted. 
    uid=0
    for polygon in polygons:
        numpyPolygon=np.array(polygon)
        delaunayTriangulation=Delaunay(numpyPolygon[:,1:], qhull_options='QbB Qx Qs Qz Qt Q12')
        
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
    # merge the extra redundant polygons that have been created when executing Delaunay
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
        #check if any problem points only have one associated triangle (Should not happen!!)
    for key in problem_points.keys():
        if len(problem_points[key])<2:            
            del problem_points[key]
    return problem_points

def eliminateFalseTriangles(cutDelaunay_path, polygons, precision, UID_field):
    problem_points=getProblemPoints(cutDelaunay_path, polygons, precision, UID_field) # points whose vertices do not coincide with gap polygon vertices. result of arcpy.Clip operation
    mergeFeatures(problem_points, cutDelaunay_path, UID_field)    
                    
def determineTriangleType(cutDelaunay_path, polygons, triangleType, precision, polygon_nr, UID_field, point_order, original_order):

    arcpy.AddField_management(cutDelaunay_path, triangleType, "SHORT")

    allPoints=extractAllPoints(polygons, precision)

    triangles=[]
    
    with arcpy.da.UpdateCursor(cutDelaunay_path, ["SHAPE@", triangleType, polygon_nr, UID_field, point_order, original_order]) as cursor:        
        for row in cursor:
            # triangle type keys.   -1 - error in determining the triangle type
            #                       0 - triangle is equal with original gap polygon
            #                       1 - triangle shares 2 sides with original gap poly, 1 extra point needed, plus the middle vertice
            #                       2 - tri shares 1 side w/ gap polygon, 2 extra points needed as middlepoints
            #                       3 - tri shares no sides w/ gap polygon, 3 middlepoints + centroid needed!
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
                for i in range(len(polygons[row[2]])-1):
                    polygonString= polygonString+ str(i)
                polygonString= polygonString*2
                row[5]=polygonString
                IDstring="".join(str(pointIDs))
                IDstring = IDstring.translate(None, ',][ ')
                row[4]=IDstring
                IDstring_sorted="".join(sorted(str(pointIDs[:-1])))
                IDstring_sorted = IDstring_sorted.translate(None, ',][ ')
                if ((polygonString.find(IDstring[:-1])!=-1 or polygonString.find(IDstring[1:])!=-1)): # triangle shares 2 sides with original gap poly
                    row[1]=1
                elif (polygonString.find(IDstring_sorted[:-1])!=-1 or polygonString.find(IDstring_sorted[1:])!=-1): #tri shares 1 side w/ gap polygon
                    row[1]=2
                elif (polygonString.find(IDstring_sorted[:-2])!=-1 or polygonString.find(IDstring_sorted[-2:])!=-1):  #tri shares no sides w/ gap polygon
                    row[1]=3
                else:
                    row[1]=-1
            cursor.updateRow(row)

def strToIntList(string):
    # Translate string to a list of ints
    myList=[]
    for element in string:
        try:
            myList.append(int(element))
        except:
            print("The string element can not be converted to int!?")
    return myList

def addTypeField(shapePath, fieldName, fieldValue):
    arcpy.AddField_management(shapePath, fieldName, 'TEXT', 10)
    with arcpy.da.UpdateCursor(shapePath, [fieldName]) as cur:
        for row in cur:
            row[0]=fieldValue
            cur.updateRow(row)

def getNeighbors(shpPath, tablePath):
    # find all neighbors, as neighbor table
    with arcpy.da.UpdateCursor(shpPath, ["OID@","Id"]) as cur:
        for row in cur:
            row[1]=row[0]
            cur.updateRow(row)
    arcpy.PolygonNeighbors_analysis(shpPath, tablePath,"Id", "NO_AREA_OVERLAP", "BOTH_SIDES", 0.001)
    print(arcpy.GetMessages())  

def determineMergeNeighbors(neighborSet):
    # from each 'hole'- polygon find the corresponding Original polyton to merge with
    for key in neighborSet:
        numpyArray = np.array(neighborSet[key])
        if np.max(numpyArray[:,1]) == 0: # the pair has no common edges! Use common nodes to determine the right neighbor
            maxNodes= np.max(numpyArray[:,2])
            neighbor=numpyArray[np.where(numpyArray[:,2] == maxNodes)][0][0]
            neighborSet[key]=neighbor
        else: # use the longest edge to determine neighbor
            maxEdge= np.max(numpyArray[:,1])
            neighbor=numpyArray[np.where(numpyArray[:,1] == maxEdge)][0][0]
            neighborSet[key]=neighbor
    return neighborSet

def restructureMergeSets(neighborSet):
    # restructure the neighbor sets so that the original Polygons are used as keys (switch values and keys).
    newSet={}
    for key in neighborSet:
        if neighborSet[key] not in newSet:
            newSet[neighborSet[key]]=[key]
        else:
            newSet[neighborSet[key]].append(key)
    return newSet

def mergeNeighbors(mergeDict, shapefile):
    # merge the neighbors, based on neighbor table
    mergeDict= restructureMergeSets(mergeDict)
    newGeometriesList=[]
    for key in mergeDict:
        mergeList=mergeDict[key]
        mergeList.append(int(key))
        mergeList.sort(reverse=True)
        geometries=[]
        try:
            for polygonId in mergeList:
                expression = u'{0} = {1}'.format(arcpy.AddFieldDelimiters(shapefile, "Id"), polygonId)
                with arcpy.da.SearchCursor(shapefile, ["SHAPE@","Id"], where_clause=expression) as cur:
                    for row in cur:
                        geometries.append(row[0])
        except:
            print ("Problem getting geometries!")
        
        while len(geometries)>1:
            newGeometry=geometries[-1].union(geometries[-2])
            geometries.insert(0, newGeometry)
            del geometries[-2:]
        for polygonId in mergeList:
            expression = u'{0} = {1}'.format(arcpy.AddFieldDelimiters(shapefile, "Id"), polygonId)
            with arcpy.da.UpdateCursor(shapefile, ["SHAPE@","Id"], where_clause=expression) as cur:
                for row in cur:
                    cur.deleteRow()
        newGeometriesList.append(geometries[0])
        cur = arcpy.da.InsertCursor(shapefile,["SHAPE@", "Type", "Id"])
        cur.insertRow([geometries[0],"Modified", -1])
        
        

def getMergeNeighbors(shapefile, neighborTable):
    # find the neighbors
    neighborSets={}
    shapefileFields=["Id", "Type"]
    tableFields=["src_Id","nbr_Id","LENGTH", "NODE_COUNT"]
    with arcpy.da.SearchCursor(neighborTable, tableFields) as table_cur:
        for table_row in table_cur:
            expression = u'{0} = {1}'.format(arcpy.AddFieldDelimiters(shapefile, shapefileFields[0]), table_row[0])
            with arcpy.da.SearchCursor(shapefile, shapefileFields, where_clause=expression) as srcShp_cur:
                for src_row in srcShp_cur:
                    if src_row[1] == "Delaunay":
                        expression = u'{0} = {1}'.format(arcpy.AddFieldDelimiters(shapefile, shapefileFields[0]), table_row[1])
                        with arcpy.da.SearchCursor(shapefile, shapefileFields, where_clause=expression) as nbrShp_cur:
                            for nbr_row in nbrShp_cur:
                                if nbr_row[1]=="Original":
                                    if table_row[0] not in neighborSets:
                                        neighborSets[table_row[0]]=[]
                                    neighborSets[table_row[0]].append(table_row[1:])
    neighborSet= determineMergeNeighbors(neighborSets)
    return neighborSets
    
def createLines(temp_path, line_shapefile, triangle_shapefile, SRS, polygon_nr, UID_field, triangleType, point_order, polygons):
    arcpy.CreateFeatureclass_management(temp_path, line_shapefile, "POLYLINE","" , "DISABLED", "DISABLED", SRS)
    lines_path=temp_path+"/"+line_shapefile
    arcpy.AddField_management(in_table=lines_path, field_name=polygon_nr, field_type='LONG', field_length=10)
    arcpy.AddField_management(in_table=lines_path, field_name=UID_field, field_type='LONG', field_length=10)

    with arcpy.da.SearchCursor(triangle_shapefile, ["SHAPE@", polygon_nr, UID_field, triangleType, point_order]) as triangle_cur:
        for triangle_row in triangle_cur:
            if triangle_row[3] > 0:
                lineVertexArray = arcpy.Array()
                triangleVertices = strToIntList(triangle_row[4])
                point_1=0
                point_2=0
                if triangle_row[3] == 1: # Get the points that are following one another. The "jump" in point indexing is the vertice where the middle has to be determined
                    middlePoint = 0
                    for index in range(len(triangleVertices)-1): # get the points that are relevant for line end at middle of vertice
                        if (triangleVertices[index]+1 != triangleVertices[index+1]):
                            minPoint = [polygons[triangle_row[1]][triangleVertices[index]][1], polygons[triangle_row[1]][triangleVertices[index]][2]]
                            maxPoint = [polygons[triangle_row[1]][triangleVertices[index+1]][1], polygons[triangle_row[1]][triangleVertices[index+1]][2]]
                            points=(minPoint,maxPoint)
                            middlePoint = getMiddlePoint(points)
                            middlePoint = arcpy.Point(middlePoint[0], middlePoint[1]) # convert to arcpy Point object
                            point_1=triangleVertices[index]
                            point_2=triangleVertices[index+1]
                            break 
                    for index in reversed(range(len(triangleVertices))): # find the point that is also a point in original polygon
                        if triangleVertices[index] == point_1 or triangleVertices[index] == point_2:
                            triangleVertices.pop(index)
                    
                    pointyPoint = [polygons[triangle_row[1]][triangleVertices[0]][1], polygons[triangle_row[1]][triangleVertices[0]][2]]
                    pointyPoint= arcpy.Point(pointyPoint[0], pointyPoint[1])
                    lineVertexArray.add(middlePoint)
                    lineVertexArray.add(pointyPoint)
                    polyline = arcpy.Polyline(lineVertexArray)
                    # insert polyline:
                    with arcpy.da.InsertCursor(temp_path + "/" + line_shapefile, ["SHAPE@", polygon_nr, UID_field]) as line_cur:
                        polyline = arcpy.Polyline(lineVertexArray)
                        line_cur.insertRow([polyline, triangle_row[1],triangle_row[2]])
                        
                if triangle_row[3] == 2: # get the two lines from whom the middle has to be extracted
                    commonPoint=0
                    triangleVertices[3]=triangleVertices[2]+1 # adjust to take into account that 0 point index follows after the last point index
                    for index in range(len(triangleVertices)-1):
                        if (triangleVertices[index]+1 == triangleVertices[index+1]): # find the point indices that are following one another
                            point_on_line_1 = [polygons[triangle_row[1]][triangleVertices[index]][1], polygons[triangle_row[1]][triangleVertices[index]][2]]
                            point_on_line_2 = [polygons[triangle_row[1]][triangleVertices[index+1]][1], polygons[triangle_row[1]][triangleVertices[index+1]][2]]
                            point_1=triangleVertices[index]
                            point_2=triangleVertices[index+1]
                            for index in reversed(range(len(triangleVertices))): # find the point that is common for both middle lines
                                if triangleVertices[index] == point_1 or triangleVertices[index] == point_2:
                                    triangleVertices.pop(index)
                            commonPoint = [polygons[triangle_row[1]][triangleVertices[0]][1], polygons[triangle_row[1]][triangleVertices[0]][2]]
                            points_1=(point_on_line_1, commonPoint)
                            points_2=(point_on_line_2, commonPoint)
                            middlePoint_1=getMiddlePoint(points_1)
                            middlePoint_2=getMiddlePoint(points_2)
                            middlePoint_1= arcpy.Point(middlePoint_1[0], middlePoint_1[1])
                            middlePoint_2= arcpy.Point(middlePoint_2[0], middlePoint_2[1])
                            break
                    lineVertexArray.add(middlePoint_1)
                    lineVertexArray.add(middlePoint_2)
                    polyline = arcpy.Polyline(lineVertexArray)
                    # insert polyline:
                    with arcpy.da.InsertCursor(temp_path + "/" + line_shapefile, ["SHAPE@", polygon_nr, UID_field]) as line_cur:
                        polyline = arcpy.Polyline(lineVertexArray)
                        line_cur.insertRow([polyline, triangle_row[1],triangle_row[2]])
                        
                if triangle_row[3] == 3: # Find the triangle centroid and middle points of all sides
                    # getting the centroid
                    lineVertexArray1 = arcpy.Array()
                    lineVertexArray2 = arcpy.Array()
                    lineVertexArray3 = arcpy.Array()
                    centroidPoint_1 = [polygons[triangle_row[1]][triangleVertices[0]][1], polygons[triangle_row[1]][triangleVertices[0]][2]]
                    centroidPoint_2 = [polygons[triangle_row[1]][triangleVertices[1]][1], polygons[triangle_row[1]][triangleVertices[1]][2]]
                    centroidPoint_3 = [polygons[triangle_row[1]][triangleVertices[2]][1], polygons[triangle_row[1]][triangleVertices[2]][2]]
                    centroidPoints =(centroidPoint_1, centroidPoint_2, centroidPoint_3)
                    centroid = getTriangleCentroid(centroidPoints)
                    centroid = arcpy.Point(centroid[0], centroid[1])
                    # getting the rest: all the middle points of the triangle sides!
                    middlePoint_1=getMiddlePoint(([polygons[triangle_row[1]][triangleVertices[0]][1], polygons[triangle_row[1]][triangleVertices[0]][2]], [polygons[triangle_row[1]][triangleVertices[1]][1], polygons[triangle_row[1]][triangleVertices[1]][2]]))
                    middlePoint_2=getMiddlePoint(([polygons[triangle_row[1]][triangleVertices[1]][1], polygons[triangle_row[1]][triangleVertices[1]][2]], [polygons[triangle_row[1]][triangleVertices[2]][1], polygons[triangle_row[1]][triangleVertices[2]][2]]))
                    middlePoint_3=getMiddlePoint(([polygons[triangle_row[1]][triangleVertices[0]][1], polygons[triangle_row[1]][triangleVertices[0]][2]], [polygons[triangle_row[1]][triangleVertices[2]][1], polygons[triangle_row[1]][triangleVertices[2]][2]]))
                    middlePoint_1= arcpy.Point(middlePoint_1[0], middlePoint_1[1])
                    middlePoint_2= arcpy.Point(middlePoint_2[0], middlePoint_2[1])
                    middlePoint_3= arcpy.Point(middlePoint_3[0], middlePoint_3[1])
                    middlePoints=[middlePoint_1, middlePoint_2, middlePoint_3]

                    # insert polyline:
                    for middlePoint in middlePoints:
                        lineVertexArray.add(middlePoint)
                        lineVertexArray.add(centroid)
                        polyline = arcpy.Polyline(lineVertexArray)
                        # insert polyline:
                        with arcpy.da.InsertCursor(temp_path + "/" + line_shapefile, ["SHAPE@", polygon_nr, UID_field]) as line_cur:
                            polyline = arcpy.Polyline(lineVertexArray)
                            line_cur.insertRow([polyline, triangle_row[1],triangle_row[2]])


                    
# MAIN

# Variables
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
cut_Delaunay="cutDelaunay.shp"
cutDelaunay_path=temp_path+"/"+cut_Delaunay
delaunayWithSkeletoid_path= temp_path+"/delaunayWithSkeletoid.shp"
line_shapefile="cutLines.shp"
linesFromPoly="linesFromPoly.shp"
line_shapefile_path=temp_path+"/"+line_shapefile
linesFromPolygon_path= temp_path+"/"+linesFromPoly
mergedLines_path= temp_path+"/mergedLines.shp"
dissolvedMergedLines_path= temp_path+"/dissolvedMergedLines.shp"
originalWithDelaunay=output_path+"/result.shp"
neighborTablePath=temp_path+"/neighborTable.dbf"
typeField="Type"
triangleType="tri_type"
precision=4
UID_field="UID"
polygon_nr="PolyNo"
point_order="Pnt_order"
original_order= "Orig_order"
pi=math.pi

# CODE

# Find gaps in polygon layer: 1) union 2) fill Gaps 3) Difference 4) To Singleparts
arcpy.Dissolve_management(input_shapefile, dissolved)
getHoles(dissolved)
arcpy.Erase_analysis(dissolved, input_shapefile, holes)
arcpy.MultipartToSinglepart_management (holes, singleparts)
polygons=extractPolygons(singleparts)

# creating the triangle shapefile
createDelaunay(temp_path,triangles, polygons, SRS, polygon_nr, UID_field, point_order , original_order)

# cut delauney with original holes to remove extras
arcpy.Clip_analysis(triangles_path, holes, cutDelaunay_path)
eliminateFalseTriangles(cutDelaunay_path, polygons, precision, UID_field)

# Draw the polygon skeletoid
determineTriangleType(cutDelaunay_path,polygons , triangleType, precision, polygon_nr, UID_field, point_order, original_order)
createLines(temp_path, line_shapefile, cutDelaunay_path, SRS, polygon_nr, UID_field, triangleType, point_order, polygons)

# transform the delaunay triangles to lines and merge with skeletoids, then transform back to polygons
arcpy.PolygonToLine_management (cutDelaunay_path, linesFromPolygon_path)
arcpy.Merge_management([line_shapefile_path, linesFromPolygon_path],mergedLines_path)
arcpy.Dissolve_management(mergedLines_path, dissolvedMergedLines_path,"","","","UNSPLIT_LINES")
arcpy.FeatureToPolygon_management(mergedLines_path, cutDelaunay_path)

# Identify featureClasses
addTypeField(cutDelaunay_path, typeField, "Delaunay")
addTypeField(input_shapefile, typeField, "Original")

# Merge original FeatureClass with prepared delaunay polygons
arcpy.Merge_management([cutDelaunay_path, input_shapefile], originalWithDelaunay)

# Determine the neighbors of original polygons
getNeighbors(originalWithDelaunay, neighborTablePath)
neighborSets=getMergeNeighbors(originalWithDelaunay, neighborTablePath)

# Merge Neighbors
mergeNeighbors(neighborSets, originalWithDelaunay)

# delete temp directory
shutil.rmtree(temp_path)

# Visualises the gap delaunay mesh
#plt.show()


