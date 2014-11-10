# -*- coding: utf-8 -*-
from flask import Flask, jsonify
import requests
import psycopg2
import numpy
import rasterio
import pyproj
import math
import os
import json
import random,string


from shapely.geometry import Point, mapping, LineString, Polygon
from shapely.ops import transform
from functools import partial

# For testing only
from fiona import collection

app = Flask(__name__)
app.debug = True

# Postgres login credentials
pg_db = "turkompisen"
pg_host = "localhost"
pg_user = "turkompisen"
pg_port = 5432


routeDriving = "https://router.project-osrm.org/"
routeSkiing = "http://178.62.235.179:8080/"

rasterPixelSize = 100


# Geometry transform function based on pyproj.transform
project = partial(
    pyproj.transform,
    pyproj.Proj(init='EPSG:4326'),
    pyproj.Proj(init='EPSG:32633'))


@app.route('/<float:lat>/<float:lon>', methods=['GET'])
def hello(lat, lon):
    #getRoutes(type, length, drivingLength, lat, lon)
    #getRoutes('walk', 15, 8, 59.7220, 10.048786)
    #getRoutes('walk', 10, 0, 59.7220, 10.048786) # MIF-hytta
    #routes = getRoutes('walk', 5, 0, 59.81761, 10.02068) # Ulevann
    routes = getRoutes('walk', 5, 0, lat, lon) # Ulevann
    #getParkingLots(59.7220, 10.048786, 20)


    return json.dumps(routes)


@app.route("/route/family/walk")
def route_family_walk():
	return "route_family_walk"

@app.route("/route/family/bike")
def route_family_bike():
	return "route_family_bike"

@app.route("/route/family/ski")
def route_family_ski():
	return "route_family_ski"


def writeOutPoints(pointArray):
    schema = { 'geometry': 'Point', 'properties': { 'name': 'str' } }
    with collection(
        "/tmp/stifinneren/points.shp", "w", "ESRI Shapefile", schema) as output:
        for point in pointArray:
            point = Point(float(point['lon']), float(point['lat']))
            output.write({
                'properties': {
                    'name': 'navn'
                },
                'geometry': mapping(point)
            })

# {walk,ski,bike}, length in km, drivingLength in minutes, start lat, start lon
def getRoutes(type, length, drivingLength, lat, lon):

    routeAlternativesArray = []
    startLocationArray = []
    optimalRoutes = []


    if drivingLength > 0:
        # Get all parking lots for hiking if drivingLength > 0
        parkingLots = getParkingLots(lat, lon, drivingLength)
        for parking in parkingLots:

            # Check distance in route calculator for all parking lots within preferred distance
            if getDrivingDistanceInMinutes(lat, lon, parking['lat'], parking['lon']) < drivingLength:
                startLocationArray.append(parking)
    else:
        startLocationArray.append({'lat':lat, 'lon':lon})


    # Loop through all start locations and get an array of potential 
    # routes at each location. 
    for startLocation in startLocationArray:
        routeAlternativesArray.extend(loopRoutes(startLocation['lat'], startLocation['lon'], length))

    # Order the routes and get the best ones
    optimalRoutes = orderRouteAlternatives(routeAlternativesArray)


    # return json with the 10 best routes
    print "Antall ruteberegninger: " , len(optimalRoutes)
    return optimalRoutes[:10]

def getDrivingDistanceInMinutes(fromLat, fromLon, toLat, toLon):

    url = routeDriving + 'viaroute?z=14&output=json&loc='+str(fromLat)+','+str(fromLon)+'&loc='+str(toLat)+','+str(toLon)+'&instructions=false'
    r = requests.get(url)
    
    drivingDistanceInMinues = r.json()['route_summary']['total_time']

    print url
    print (drivingDistanceInMinues/60)

    # Return in minutes
    return (drivingDistanceInMinues/60)



def loopRoutes(lat, lon, length): 
    routeArray = []

    # Reproject to UTM33
    fromProj = pyproj.Proj(init='epsg:4258')
    toProj = pyproj.Proj(init='epsg:32633')
    x, y = pyproj.transform(fromProj, toProj, lon, lat)

    # Get bounds of image
    maxX = x + length*1000*1.3;
    maxY = y + length*1000*1.3;
    minX = x - length*1000*1.3;
    minY = y - length*1000*1.3;

    # Reproject back to Spherical Mercator
    toProj = pyproj.Proj(init='epsg:3857')
    fromProj = pyproj.Proj(init='epsg:32633')
    maxX, maxY = pyproj.transform(fromProj, toProj, maxX, maxY)
    minX, minY = pyproj.transform(fromProj, toProj, minX, minY)
    maxX = str(maxX)
    maxY = str(maxY)
    minX = str(minX)
    minY = str(minY)

    # Create random fileID
    randomId = "".join(random.sample(string.letters+string.digits, 8))

    # Extract skiløyper to shape file
    geom = "ST_GeomFromText('POLYGON(("+minX+" "+minY+", "+minX+" "+maxY+", "+maxX+" "+maxY+", "+maxX+" "+minY+", "+minX+" "+minY+"))')"
    command = """ 
    /Library/Frameworks/GDAL.framework/Versions/1.11/Programs/ogr2ogr -s_srs EPSG:900913 -t_srs EPSG:32633 -f "ESRI Shapefile" /tmp/stifinneren/ski_""" +str(randomId)+ """.shp PG:"host=localhost user=turkompisen dbname=turkompisen" -sql "SELECT way FROM skiloype_lengde where way && """ +geom+ """ "
    """
    os.system(command)

    command = "gdal_rasterize -tr "+str(rasterPixelSize)+" "+str(rasterPixelSize)+" -burn 255 /tmp/stifinneren/ski_"+str(randomId)+".shp /tmp/stifinneren/ski_"+str(randomId)+".tif"
    os.system(command)

    dataset = rasterio.open('/tmp/stifinneren/ski_'+str(randomId)+'.tif')
    dataset.shape
    image = dataset.read()

    # Få koordinat på første pixel
    col, row = 0, 0
    xStartImage, yStartImage = dataset.affine * (col, row)

    # Beregn antall piksler til startpunkt på ruta
    xDiffPixels = (int)(math.floor((x-xStartImage)/100))
    yDiffPixels = (int)(math.floor((yStartImage-y)/100))

    ## Regn tilbake for å sjekke at vi er på ca samme sted fortsatt
    #xStartRoute, yStartRoute = dataset.affine * (xDiffPixels, yDiffPixels)
    #print "X: " , x , xStartRoute
    #print "Y: " , y , yStartRoute

    # boundingYPixel = yStartPunkt i piksler - (lengdeFraBruker * 0.6 * 1000/100)
    # Ganger med 0.6 fordi vi trenger ikke å gå så langt ut som hele lengden. Må minium tilbake samme vei. 
    # Ganger med 1000 for å få meter 
    # Deler med 100 som er pixelstørrelsen i bildet. 



    # Get top left corner of image
    boundingYPixel = yDiffPixels-(length*0.6*1000/100)
    boundingXPixelLeft = xDiffPixels-(length*0.6*1000/100)
    imageTopLeft = image[0][boundingYPixel:yDiffPixels, boundingXPixelLeft:xDiffPixels]
    print "imageTopLeft"
    print imageTopLeft


    # Get top right corner of image
    boundingXPixelRight = xDiffPixels+(length*0.6*1000/100)
    imageTopRight = image[0][boundingYPixel:yDiffPixels, xDiffPixels:boundingXPixelRight]
    print "\nimageTopRight"
    print imageTopRight

    # Get bottom left corner of image
    boundingYPixel = yDiffPixels+(length*0.6*1000/100)
    boundingXPixelLeft= xDiffPixels-(length*0.6*1000/100)
    imageBottomLeft = image[0][yDiffPixels:boundingYPixel, boundingXPixelLeft:xDiffPixels]
    print "\nimageBottomLeft"
    print imageBottomLeft

    # Get bottom right corner of image
    boundingYPixel = yDiffPixels+(length*0.6*1000/100)
    boundingXPixelRight = xDiffPixels+(length*0.6*1000/100)
    imageBottomRight = image[0][yDiffPixels:boundingYPixel, xDiffPixels:boundingXPixelRight]
    print "\nimageBottomRight"
    print imageBottomRight

    # Do it for all quadrants
    routeArray.extend(getPossibleRoute(lat, lon, dataset, imageTopLeft, boundingXPixelLeft, boundingYPixel, imageTopRight, xDiffPixels, boundingYPixel))
    routeArray.extend(getPossibleRoute(lat, lon, dataset, imageTopLeft, boundingXPixelLeft, boundingYPixel, imageBottomLeft, boundingXPixelLeft, yDiffPixels))
    routeArray.extend(getPossibleRoute(lat, lon, dataset, imageBottomLeft, boundingXPixelLeft, yDiffPixels, imageBottomRight, xDiffPixels, yDiffPixels))
    routeArray.extend(getPossibleRoute(lat, lon, dataset, imageBottomRight, xDiffPixels, yDiffPixels, imageTopRight, xDiffPixels, boundingYPixel))
    #print len(routeArray)
    #print "Dataset shape: " , image[0].shape
    #writeOutPoints(routeArray)
    return routeArray

def getPossibleRoute(lat, lon, dataset, arrayOne, xdiffOne, ydiffOne, arrayTwo, xdiffTwo, ydiffTwo):
    routeArray = []

    arrayOneSkip = 0
    arrayTwoSkip = 0

    # Skip some values 
    if arrayOne.size<50:
        arrayOneSkipValue = math.floor(arrayOne.size*0.9)
        arrayTwoSkipValue = math.floor(arrayTwo.size*0.9)
    else: 
        arrayOneSkipValue = 50
        arrayTwoSkipValue = 50

    print "Size: " , arrayOneSkipValue

    for (arrayOneY,arrayOneX), value in numpy.ndenumerate(arrayOne):
        arrayTwoSkip = 0
        if arrayOne[arrayOneY][arrayOneX] == 255:
            arrayOneSkip += 1
            if arrayOneSkip == arrayOneSkipValue:
                arrayOneSkip = 0

                for (arrayTwoY,arrayTwoX), value in numpy.ndenumerate(arrayTwo):
                    if arrayTwo[arrayTwoY][arrayTwoX] == 255: 
                        arrayTwoSkip += 1
                        if arrayTwoSkip == arrayTwoSkipValue:
                            arrayTwoSkip = 0

                            # Beregn koordinater. Her må vi forskyve litt på delbildene vi har tatt ut av arrayet
                            markerLeftXCoordinate, markerLeftYCoordinate = dataset.affine * (xdiffOne+arrayOneX, ydiffOne+arrayOneY)
                            markerRightXCoordinate, markerRightYCoordinate = dataset.affine * (xdiffTwo+arrayTwoX, ydiffTwo+arrayTwoY)
                            
                            # Add half a pixel to get to center
                            markerLeftXCoordinate += rasterPixelSize/2
                            markerLeftYCoordinate -= rasterPixelSize/2
                            markerRightXCoordinate += rasterPixelSize/2
                            markerRightYCoordinate -= rasterPixelSize/2                          

                            # Reproject to WGS84
                            wgs84 = pyproj.Proj(init='epsg:4258')
                            utm33 = pyproj.Proj(init='epsg:32633')
                            markerLeftXCoordinate, markerLeftYCoordinate = pyproj.transform(utm33, wgs84, markerLeftXCoordinate, markerLeftYCoordinate)
                            markerRightXCoordinate, markerRightYCoordinate = pyproj.transform(utm33, wgs84, markerRightXCoordinate, markerRightYCoordinate)
                            
                            # Testing outputting points to file
                            #routeArray.append({"startPoint": [lat,lon],"endPoint": [lat,lon],"viaPoint1": [markerLeftYCoordinate,markerLeftXCoordinate],"viaPoint2": [markerRightYCoordinate,markerRightXCoordinate]})
        

                            ## Do the route calculation
                            r = calculateRoute(lat, lon, markerLeftYCoordinate, markerLeftXCoordinate, markerRightYCoordinate, markerRightXCoordinate)
                            if r.json()['status'] == 0:
                                instructions = r.json()['route_instructions']
                                geometry = r.json()['route_geometry']
                                
                                # Convert to coordinate tuples
                                coordinates = decode(geometry)
                                
                                # Convert to line
                                line = LineString(coordinates)
                                utm33Line = transform(project, line)
                                b = utm33Line.bounds

                                # Convert line bbox to polygon
                                polygon = Polygon([ (b[0], b[1]) , (b[0], b[3]), (b[2], b[3]), (b[2], b[1]) ])
                                
                                # Get total distance of non ski track segment
                                nonSkiTrackLength = 0
                                for segment in instructions:
                                    featureType = segment[1]
                                    if featureType != "skiing":
                                        nonSkiTrackLength = nonSkiTrackLength + segment[2]

                                # # Sjekk at ruta er ei runde og ikke for mye fram og tilbake. 
                                # # Fram og tilbake er OK, men skårer færre poeng

                                # # Sjekk at alle viapunkter er på skiløyper. Hvis ikke vil vi sannsynligvis
                                # # ikke ha med turen. 

                                # Only append route if there is not to many non ski track segments on route. 
                                routeSummary = r.json()['route_summary']
                                print "Total distance: ", routeSummary['total_distance']
                                print "Non skiing distance: " , nonSkiTrackLength
                                print "Divided: ", float(nonSkiTrackLength) / float(routeSummary['total_distance'])
                                if float(nonSkiTrackLength) / float(routeSummary['total_distance']) < 1:
                                    routeArray.append({"distance": utm33Line.length, "bbox-area": polygon.area ,  "startPoint": [lat,lon],"endPoint": [lat,lon],"viaPoint1": [markerLeftYCoordinate,markerLeftXCoordinate],"viaPoint2": [markerRightYCoordinate,markerRightXCoordinate]})
                                else:
                                    print "TAR IKKE MED!"

    return routeArray


def calculateRoute(startLat, startLon, markerLeftLat, markerLeftLon, markerRightLat, markerRightLon):

    url = 'viaroute?output=json&loc='+str(startLat)+','+str(startLon)+'&loc='+str(markerLeftLat)+','+str(markerLeftLon)+'&loc='+str(markerRightLat)+','+str(markerRightLon)+'&instructions=true'
    print routeSkiing + url
    r = requests.get(routeSkiing + url)
    
    return r


def orderRouteAlternatives(routeAlternativesArray):

    # Remove duplicate bbox area
    # We consider these as the same route suggestion
    noDuplicatesList = []
    a = routeAlternativesArray

    bboxAreaList = []
    for route in routeAlternativesArray:
        bboxAreaList.append(route['bbox-area'])

    for i in range(0, len(bboxAreaList)):
        if bboxAreaList[i] not in bboxAreaList[i+1:]:
            noDuplicatesList.append(routeAlternativesArray[i])

    
    # Sort by bbox area
    # http://stackoverflow.com/questions/72899/how-do-i-sort-a-list-of-dictionaries-by-values-of-the-dictionary-in-python
    sortedByBboxArea = sorted(noDuplicatesList, key=lambda k: k['bbox-area'])
    sortedByBboxArea.reverse()


    # Find non circular routes

    optimalRoutes = sortedByBboxArea

    return optimalRoutes


def getParkingLots(lat, lon, drivingLength):

    # Recalculate from minues to length in km. 
    # 1.5 km per minute is approxiamatly 90 km/h
    distanceInKm = drivingLength * 1.5
    print distanceInKm*1000

    try:
        conn = psycopg2.connect("dbname="+pg_db+" user="+pg_user+" host="+pg_host+" ")
    except:
        print "Could not connect to database " + pg_db
        
    cursor = conn.cursor()


    parkingLotsJson = []
    # Get all parking lots within specified distance
    sqlParking = """select st_x(st_transform(way, 4326)), st_y(st_transform(way,4326)) from poi p 
                    where p.amenity='parking' and p.hiking='yes'
                    and st_dwithin(st_transform(p.way, 32633), 
                    st_transform(ST_GeomFromText('POINT(%s %s)',4326), 32633),%s)"""

    print sqlParking
    #print lon
    #print lat
    #print distanceInKm*1000
    
    cursor.execute(sqlParking, (lon, lat, distanceInKm*1000))
    
    parkingLots = cursor.fetchall()
    conn.commit();

    # Convert to dict
    for parking in parkingLots:
        parkingLotsJson.append({'lat':parking[1], 'lon':parking[0]})

    return parkingLotsJson

def encode_coords(coords):
    '''Encodes a polyline using Google's polyline algorithm
    
    See http://code.google.com/apis/maps/documentation/polylinealgorithm.html 
    for more information.
    
    :param coords: Coordinates to transform (list of tuples in order: latitude, 
    longitude).
    :type coords: list
    :returns: Google-encoded polyline string.
    :rtype: string    
    '''
    
    result = []
    
    prev_lat = 0
    prev_lng = 0
    
    for x, y in coords:        
        lat, lng = int(y * 1e5), int(x * 1e5)
        
        d_lat = _encode_value(lat - prev_lat)
        d_lng = _encode_value(lng - prev_lng)        
        
        prev_lat, prev_lng = lat, lng
        
        result.append(d_lat)
        result.append(d_lng)
    
    return ''.join(c for r in result for c in r)
    
def _split_into_chunks(value):
    while value >= 32: #2^5, while there are at least 5 bits
        
        # first & with 2^5-1, zeros out all the bits other than the first five
        # then OR with 0x20 if another bit chunk follows
        yield (value & 31) | 0x20 
        value >>= 5
    yield value
 
def _encode_value(value):
    # Step 2 & 4
    value = ~(value << 1) if value < 0 else (value << 1)
    
    # Step 5 - 8
    chunks = _split_into_chunks(value)
    
    # Step 9-10
    return (chr(chunk + 63) for chunk in chunks)
 
def decode(point_str):
    '''Decodes a polyline that has been encoded using Google's algorithm
    http://code.google.com/apis/maps/documentation/polylinealgorithm.html
    
    This is a generic method that returns a list of (latitude, longitude) 
    tuples.
    
    :param point_str: Encoded polyline string.
    :type point_str: string
    :returns: List of 2-tuples where each tuple is (latitude, longitude)
    :rtype: list
    
    '''
            
    # sone coordinate offset is represented by 4 to 5 binary chunks
    coord_chunks = [[]]
    for char in point_str:
        
        # convert each character to decimal from ascii
        value = ord(char) - 63
        
        # values that have a chunk following have an extra 1 on the left
        split_after = not (value & 0x20)         
        value &= 0x1F
        
        coord_chunks[-1].append(value)
        
        if split_after:
                coord_chunks.append([])
        
    del coord_chunks[-1]
    
    coords = []
    
    for coord_chunk in coord_chunks:
        coord = 0
        
        for i, chunk in enumerate(coord_chunk):                    
            coord |= chunk << (i * 5) 
        
        #there is a 1 on the right if the coord is negative
        if coord & 0x1:
            coord = ~coord #invert
        coord >>= 1
        coord /= 100000.0
                    
        coords.append(coord)
    
    # convert the 1 dimensional list to a 2 dimensional list and offsets to 
    # actual values
    points = []
    prev_x = 0
    prev_y = 0
    for i in xrange(0, len(coords) - 1, 2):
        if coords[i] == 0 and coords[i + 1] == 0:
            continue
        
        prev_x += coords[i + 1]
        prev_y += coords[i]
        # a round to 6 digits ensures that the floats are the same as when 
        # they were encoded
        points.append((round(prev_x, 6)/10, round(prev_y, 6)/10))
    
    return points   

if __name__ == "__main__":
    app.run()



