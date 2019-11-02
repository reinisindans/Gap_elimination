# Gap_elimination
Reinis Indans
01.11.2019

### **This python script eliminates holes between polygons, dividing the gap area between all neighboring polygons.**

Written in Python
Arcmap licence needed!


To execute the script, place the gaps.py file in the folder with your shapefile (of the other way around...), and execute the script. 
No adjusting of working directories necessary.
There can be only one shapefile in the directory with gaps.py file.


## Algorithm

1. Find the hole polygons
2. Create Delaunay-triangles based on the found holes
3. Creates a polygon-skeleton of each hole polygon
4. Cuts the Delaunay-polygon with polygon- skeletons
5. The resulting polygons are added to relevant neighbor polygons from the original data set 

## Output

A polygon layer with holes filled. Is being places in ./Output directory.
