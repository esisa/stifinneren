# -*- coding: utf-8 -*-
from shapely.geometry import Point, mapping, LineString, Polygon
from shapely.ops import transform
from functools import partial
from shapely.ops import cascaded_union


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


# For testing only
from fiona import collection

# For multiprocess URLS
import grequests

# To process URLS i batch
from itertools import islice, chain
def batch(iterable, size):
    sourceiter = iter(iterable)
    while True:
        batchiter = islice(sourceiter, size)
        yield chain([batchiter.next()], batchiter)


app = Flask(__name__)
app.debug = False

# Postgres login credentials
pg_db = "turkompisen"
pg_host = "localhost"
pg_user = "turkompisen"
pg_port = 5432

backendBaseURL = "http://backend.turkompisen.no"


routeDriving = "https://router.project-osrm.org/"
routeOSMSki = "http://backend.turkompisen.no/route/no/osm/ski/"
routeKartverketHike =  "http://backend.turkompisen.no/route/no/kartverket/tur/"
routeOSMHike = "http://backend.turkompisen.no/route/no/osm/tur/"
routeKartverketSki =  "http://backend.turkompisen.no/route/no/kartverket/ski/"

rasterPixelSize = 100
checksum = ""
checkSumHintStartCoordinate = ""

urls = []

routeType = "kartverket"

skiingViaPointTables = [
    'skiloype_lengde_centroid_5000',
    'skiloype_lengde_centroid_4000',
    'skiloype_lengde_centroid_3000',
    'skiloype_lengde_centroid_2500',
    'skiloype_lengde_centroid_2000',
    'skiloype_lengde_centroid_1500',
    'skiloype_lengde_centroid_1000',
    'skiloype_lengde_centroid_500',
    'skiloype_lengde_centroid_100',
    'skiloype_lengde_centroid'
]

kartverketViaPointTables = [
    'kartverket_n50_sti_centroid_5000',
    'kartverket_n50_sti_centroid_4000',
    'kartverket_n50_sti_centroid_3000',
    'kartverket_n50_sti_centroid_2500',
    'kartverket_n50_sti_centroid_2000',
    'kartverket_n50_sti_centroid_1500',
    'kartverket_n50_sti_centroid_1000',
    'kartverket_n50_sti_centroid_500',
    'kartverket_n50_sti_centroid_100',
    'kartverket_n50_sti_centroid'
]

# Geometry transform function based on pyproj.transform
project = partial(
    pyproj.transform,
    pyproj.Proj(init='EPSG:4326'),
    pyproj.Proj(init='EPSG:32633'))
    
@app.route("/route/kartverket/hike/<float:startLat>/<float:startLon>/<float:endLat>/<float:endLon>")
def route_kartverket_walk(startLat, startLon, endLat, endLon):
    result = calcSimpleRoute(routeKartverketHike, startLat, startLon, endLat, endLon)
    return json.dumps(result)

@app.route("/route/kartverket/ski/<float:startLat>/<float:startLon>/<float:endLat>/<float:endLon>")
def route_kartverket_ski(startLat, startLon, endLat, endLon):
    result = calcSimpleRoute(routeKartverketSki, startLat, startLon, endLat, endLon)
    return json.dumps(result)

@app.route("/route/osm/hike/<float:startLat>/<float:startLon>/<float:endLat>/<float:endLon>")
def route_osm_walk(startLat, startLon, endLat, endLon):
    result = calcSimpleRoute(routeOSMHike, startLat, startLon, endLat, endLon)
    return json.dumps(result)

@app.route("/route/osm/ski/<float:startLat>/<float:startLon>/<float:endLat>/<float:endLon>")
def route_osm_ski(startLat, startLon, endLat, endLon):
    result = calcSimpleRoute(routeOSMSki, startLat, startLon, endLat, endLon)
    return json.dumps(result)


def calcSimpleRoute(baseURL, startLat, startLon, endLat, endLon):

    routeTypes = { "barn":      {"hike": 2, "ski": 4, "bicycle": 7}, 
                   "mosjonist": {"hike": 3, "ski": 7, "bicycle": 10}, 
                   "barnevogn": {"hike": 2, "ski": 4, "bicycle": 7}, 
                   "blodsprek": {"hike": 4, "ski": 10, "bicycle": 15} 
                  }
    
    # Make request
    url = baseURL + 'viaroute?z=22&alt=false&output=json&loc='+str(startLat)+','+str(startLon)+'&loc='+str(endLat)+','+str(endLon)
    r = requests.get(url)
    result = r.json()

    # Get place names
    fromPlaceName = getPlaceForPoint(startLat, startLon)
    toPlaceName = getPlaceForPoint(endLat, endLon)
    result['route_summary']['from_place_name'] = fromPlaceName
    result['route_summary']['to_place_name'] = toPlaceName
    
    # Parse geom
    coordinates = decode(result['route_geometry'])
    line = LineString(coordinates)

    # Get bounding box
    minLon, minLat, maxLon, maxLat = line.bounds
    result['route_summary']['boundingBox'] = { "minLat": minLat,
                                               "minLon": minLon,
                                               "maxLat": maxLat,
                                               "maxLon": maxLon  
                                              }

    # Get time spent route
    hours = math.floor((result['route_summary']['total_distance']/1000)/routeTypes['mosjonist']['hike'])
    min = 22
    result['route_summary']['time'] = {"hours": hours, "min": min}

    # Get elevation data
    result['elev_geometry'] = getElevationProfile(line)

    # Get height meters up and down

    return result


@app.route('/circularRoute/<float:lat>/<float:lon>', methods=['GET'])
def hello(lat, lon):
    global urls
    urls = []
    #getRoutes(type, length, drivingLength, lat, lon)
    #getRoutes('walk', 15, 8, 59.7220, 10.048786)
    #getRoutes('walk', 10, 0, 59.7220, 10.048786) # MIF-hytta
    #routes = getRoutes('walk', 5, 0, 59.81761, 10.02068) # Ulevann
    routes = getRoutes('walk', 15, 0, lat, lon) 
    #getParkingLots(59.7220, 10.048786, 20)


    return json.dumps(routes)

@app.route('/circularRoute/<float:lat>/<float:lon>/<int:length>/', methods=['GET'])
def getRoutes(lat, lon, length):
    global urls
    urls = []
    #getRoutes(type, length, drivingLength, lat, lon)
    #getRoutes('walk', 15, 8, 59.7220, 10.048786)
    #getRoutes('walk', 10, 0, 59.7220, 10.048786) # MIF-hytta
    #routes = getRoutes('walk', 5, 0, 59.81761, 10.02068) # Ulevann
    routes = getRoutes('walk', length, 0, lat, lon) 
    #getParkingLots(59.7220, 10.048786, 20)


    return json.dumps(routes)

def getPlaceForPoint(lat, lon):

    accectedPlaces = ['kafe', 'Betjent', 'Ubetjent', 'Selvbetjent', 'Koie']

    # Make request
    url = backendBaseURL + '/turkompisenSearch/feature/' + str(lat) + '/' + str(lon) + '/20'
    r = requests.get(url)
    result = r.json()

    # Default name
    name = None

    hits = result['hits']['hits']
    for hit in hits:
        if hit['_source']['type'] in accectedPlaces:
            name = hit['_source']['name']
            

    if name == None:
        url = backendBaseURL + '/turkompisenSearch/reverse/' + str(lat) + '/' + str(lon)
        r = requests.get(url)
        result = r.json()
        hits = result['hits']['hits']
        for hit in hits:
            name = hit['_source']['name']
            break # Only take first result

    if name == None:
        name = "Ukjent"

    return name

def getElevationProfile(routeGeom):
    return ""


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
    optimalRoutes = orderRouteAlternatives(routeAlternativesArray, length)

    # return json with the 10 best routes
    print "Antall ruter etter filtrering: " , len(optimalRoutes)
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
    global routeType
    routeArray = []

    # Reproject to UTM33
    fromProj = pyproj.Proj(init='epsg:4258')
    toProj = pyproj.Proj(init='epsg:32633')
    x, y = pyproj.transform(fromProj, toProj, lon, lat)

    # Get bounds of image
    # TODO: Justere på 1.3 for å se om den kan være lavere og fortsatt få lange nok turer
    maxX = x + length*1000*0.2;
    maxY = y + length*1000*0.2;
    minX = x - length*1000*0.2;
    minY = y - length*1000*0.2;

    #print "Center lon lat: " , lon, lat
    #print "Center x    y: " , x, y
    #print maxX, maxY, minX, minY

    # Reproject back to Spherical Mercator
    toProj = pyproj.Proj(init='epsg:3857')
    fromProj = pyproj.Proj(init='epsg:32633')
    maxX, maxY = pyproj.transform(fromProj, toProj, maxX, maxY)
    minX, minY = pyproj.transform(fromProj, toProj, minX, minY)
    maxX = str(maxX)
    maxY = str(maxY)
    minX = str(minX)
    minY = str(minY)

    if routeType == 'kartverket':
        viaPointTables = kartverketViaPointTables
    else:
        viaPointTables = skiingViaPointTable

    for skiingViaPointTable in kartverketViaPointTables:

        print "Beregningsnivå: " , skiingViaPointTable

        # Create folder if does not exist
        if not os.path.exists("/tmp/stifinneren"):
            os.makedirs("/tmp/stifinneren")

        # Create random fileID
        randomId = "".join(random.sample(string.letters+string.digits, 8))

        # Extract skiløyper to shape file
        geom = "ST_GeomFromText('POLYGON(("+minX+" "+minY+", "+minX+" "+maxY+", "+maxX+" "+maxY+", "+maxX+" "+minY+", "+minX+" "+minY+"))')"
        command = """ 
        /Library/Frameworks/GDAL.framework/Versions/1.11/Programs/ogr2ogr -s_srs EPSG:900913 -t_srs EPSG:32633 -f "ESRI Shapefile" /tmp/stifinneren/ski_""" +str(randomId)+ """.shp PG:"host=localhost user=turkompisen dbname=turkompisen" -sql "SELECT way FROM """+skiingViaPointTable+""" where way && """ +geom+ """ "
        """
        print command
        os.system(command)

        command = "gdal_rasterize -tr "+str(rasterPixelSize)+" "+str(rasterPixelSize)+" -burn 255 /tmp/stifinneren/ski_"+str(randomId)+".shp /tmp/stifinneren/ski_"+str(randomId)+".tif"
        os.system(command)

        numViaPoints = 0
        try:
            dataset = rasterio.open('/tmp/stifinneren/ski_'+str(randomId)+'.tif')
            imageYDim, imageXDim = dataset.shape
            image = dataset.read()

            for (v,w), value in numpy.ndenumerate(image[0]):
                if image[0][v][w] == 255:
                    numViaPoints = numViaPoints + 1
            print "Antall viapunkter: " , numViaPoints
        except IOError, e:
            print e.errno
            print e
        

        if numViaPoints > 15:
            break

    # If no viapoints is found then dataset will throw a NameError
    try:
    
        # Få koordinat på første pixel
        col, row = 0, 0
        xStartImage, yStartImage = dataset.affine * (col, row)

        # Beregn antall piksler til startpunkt på ruta
        centerPixelX = (int)(math.floor((x-xStartImage)/rasterPixelSize))
        centerPixelY = (int)(math.floor((yStartImage-y)/rasterPixelSize))

        ## Regn tilbake for å sjekke at vi er på ca samme sted fortsatt
        #xStartRoute, yStartRoute = dataset.affine * (centerPixelX, centerPixelY)
        #print "X: " , x , xStartRoute
        #print "Y: " , y , yStartRoute

        # boundingYPixel = yStartPunkt i piksler - (lengdeFraBruker * 0.6 * 1000/100)
        # Ganger med 0.6 fordi vi trenger ikke å gå så langt ut som hele lengden. Må minium tilbake samme vei. 
        # Ganger med 1000 for å få meter 
        # Deler med 100 som er pixelstørrelsen i bildet. 


        # Calculate pixel bounds
        topMostYPixel = centerPixelY-(length*0.99*1000/rasterPixelSize) 
        leftMostXPixel = centerPixelX-(length*0.99*1000/rasterPixelSize)
        rightMostXPixel = centerPixelX+(length*0.99*1000/rasterPixelSize)
        bottomMostYPixel = centerPixelY+(length*0.99*1000/rasterPixelSize)
        
        # Make sure we do not go outside of image 
        if topMostYPixel<0:
            topMostYPixel=0
        if leftMostXPixel<0:
            leftMostXPixel=0
        if rightMostXPixel>imageXDim:
            rightMostXPixel=imageXDim
        if bottomMostYPixel>imageYDim:
            bottomMostYPixel=imageYDim

        # Get top left corner of image
        imageTopLeft = image[0][topMostYPixel:centerPixelY, leftMostXPixel:centerPixelX]
        i = 0
        for (y,x), value in numpy.ndenumerate(imageTopLeft):
            if imageTopLeft[y][x] == 255:
                i = i + 1
        print "imageTopLeft: " , i
        #print imageTopLeft 
        col, row = leftMostXPixel, topMostYPixel
        xStartImage, yStartImage = dataset.affine * (col, row)
        #print "Top left coordinate: ", xStartImage, yStartImage

        # Get top right corner of image
        imageTopRight = image[0][topMostYPixel:centerPixelY, centerPixelX:rightMostXPixel]
        i = 0
        for (y,x), value in numpy.ndenumerate(imageTopRight):
            if imageTopRight[y][x] == 255:
                i = i + 1
        print "\nimageTopRight: ", i
        #print imageTopRight

        # Get bottom left corner of image
        imageBottomLeft = image[0][centerPixelY:bottomMostYPixel, leftMostXPixel:centerPixelX]
        i = 0
        for (y,x), value in numpy.ndenumerate(imageBottomLeft):
            if imageBottomLeft[y][x] == 255:
                i = i + 1
        print "\nimageBottomLeft: " , i
        #print imageBottomLeft

        # Get bottom right corner of image
        imageBottomRight = image[0][centerPixelY:bottomMostYPixel, centerPixelX:rightMostXPixel]
        i = 0
        for (y,x), value in numpy.ndenumerate(imageBottomRight):
            if imageBottomRight[y][x] == 255:
                i = i + 1
        print "\nimageBottomRight: " , i
        #print imageBottomRight

        # Do it for all quadrants
        routeArray.extend(getPossibleRoute(lat, lon, dataset, imageTopLeft, leftMostXPixel, topMostYPixel, imageTopRight, centerPixelX, topMostYPixel))
        routeArray.extend(getPossibleRoute(lat, lon, dataset, imageTopLeft, leftMostXPixel, topMostYPixel, imageBottomLeft, leftMostXPixel, centerPixelY))
        routeArray.extend(getPossibleRoute(lat, lon, dataset, imageBottomLeft, leftMostXPixel, centerPixelY, imageBottomRight, centerPixelX, centerPixelY))
        routeArray.extend(getPossibleRoute(lat, lon, dataset, imageBottomRight, centerPixelX, centerPixelY, imageTopRight, centerPixelX, topMostYPixel))
        
        routeArray.extend(getPossibleRoute(lat, lon, dataset, imageTopLeft, leftMostXPixel, topMostYPixel, imageTopLeft, leftMostXPixel, topMostYPixel))
        routeArray.extend(getPossibleRoute(lat, lon, dataset, imageBottomLeft, leftMostXPixel, centerPixelY, imageBottomLeft, leftMostXPixel, centerPixelY))
        routeArray.extend(getPossibleRoute(lat, lon, dataset, imageBottomRight, centerPixelX, centerPixelY, imageBottomRight, centerPixelX, centerPixelY))
        routeArray.extend(getPossibleRoute(lat, lon, dataset, imageTopRight, centerPixelX, topMostYPixel, imageTopRight, centerPixelX, topMostYPixel, True))
        
        #print len(routeArray)
        #print "Dataset shape: " , image[0].shape
        #writeOutPoints(routeArray)
        return routeArray
    except NameError:
      return routeArray
    

def getPossibleRoute(lat, lon, dataset, arrayOne, xdiffOne, ydiffOne, arrayTwo, xdiffTwo, ydiffTwo, lastCalc=False):
    global checksum
    global checkSumHintStartCoordinate
    checkSumHintViaPoint1 = ""
    global urls
    global routeType

    routeArray = []

    arrayOneSkip = 0
    arrayTwoSkip = 0

    # Skip some values 
    if arrayOne.size<50:
        arrayOneContinueValue = math.floor(arrayOne.size*0.9)
        arrayTwoContinueValue = math.floor(arrayTwo.size*0.9)
    else: 
        arrayOneContinueValue = 15
        arrayTwoContinueValue = 15

    arrayOneContinueValue = 0
    for (y,x), value in numpy.ndenumerate(arrayOne):
        if arrayOne[y][x] == 255:
            arrayOneContinueValue = arrayOneContinueValue + 1
    arrayOneContinueValue = math.floor(arrayOneContinueValue/6.5)
    arrayOneContinueValue = 1

    arrayTwoContinueValue = 0
    for (y,x), value in numpy.ndenumerate(arrayTwo):
        if arrayTwo[y][x] == 255:
            arrayTwoContinueValue = arrayTwoContinueValue + 1
    arrayTwoContinueValue = math.floor(arrayTwoContinueValue/6.5)
    arrayTwoContinueValue = 1

    #arrayOneContinueValue = 3
    #arrayTwoContinueValue = 3
    #print "Size: " , arrayOneContinueValue, arrayTwoContinueValue

    for (arrayOneY,arrayOneX), value in numpy.ndenumerate(arrayOne):
        arrayTwoSkip = 0
        if arrayOne[arrayOneY][arrayOneX] == 255:
            checkSumHintViaPoint1 = ""
            #print "Første array: " , arrayOne[arrayOneY][arrayOneX]
            arrayOneSkip += 1
            if arrayOneSkip == arrayOneContinueValue:
                arrayOneSkip = 0

                for (arrayTwoY,arrayTwoX), value in numpy.ndenumerate(arrayTwo):
                    if arrayTwo[arrayTwoY][arrayTwoX] == 255: 
                        #print "Andre array: " , arrayTwo[arrayTwoY][arrayTwoX]
                        arrayTwoSkip += 1
                        if arrayTwoSkip == arrayTwoContinueValue:
                            arrayTwoSkip = 0

                            # Beregn koordinater. Her må vi forskyve litt på delbildene vi har tatt ut av arrayet
                            markerLeftXCoordinate, markerLeftYCoordinate = dataset.affine * (xdiffOne+arrayOneX+1, ydiffOne+arrayOneY+1)
                            markerRightXCoordinate, markerRightYCoordinate = dataset.affine * (xdiffTwo+arrayTwoX+1, ydiffTwo+arrayTwoY+1)
                            #print xdiffOne, ydiffOne
                            #print arrayOneX+1, arrayOneY+1
                            #print markerLeftXCoordinate, markerLeftYCoordinate

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
                            #r = calculateRoute(lat, lon, markerLeftYCoordinate, markerLeftXCoordinate, markerRightYCoordinate, markerRightXCoordinate)
                            
                            if False: #checksum != "":
                                if False: #checkSumHintViaPoint1 != "":
                                    url = 'viaroute?output=json&checksum='+str(checksum)+'&loc='+str(lat)+','+str(lon)+'&hint='+str(checkSumHintStartCoordinate)+'&loc='+str(markerLeftYCoordinate)+','+str(markerLeftXCoordinate)+'&hint='+str(checkSumHintViaPoint1)+'&loc='+str(markerRightYCoordinate)+','+str(markerRightXCoordinate)+'&loc='+str(lat)+','+str(lon)+'&hint='+str(checkSumHintStartCoordinate)+'&instructions=true'
                                else:
                                    url = 'viaroute?output=json&checksum='+str(checksum)+'&loc='+str(lat)+','+str(lon)+'&hint='+str(checkSumHintStartCoordinate)+'&loc='+str(markerLeftYCoordinate)+','+str(markerLeftXCoordinate)+'&loc='+str(markerRightYCoordinate)+','+str(markerRightXCoordinate)+'&loc='+str(lat)+','+str(lon)+'&hint='+str(checkSumHintStartCoordinate)+'&instructions=true'
                            else:
                                url = 'viaroute?output=json&loc='+str(lat)+','+str(lon)+'&loc='+str(markerLeftYCoordinate)+','+str(markerLeftXCoordinate)+'&loc='+str(markerRightYCoordinate)+','+str(markerRightXCoordinate)+'&loc='+str(lat)+','+str(lon)+'&instructions=true'
                            
                            if routeType == 'kartverket':
                                urls.append(routeKartverketHike + url)
                            else:
                                urls.append(routeOSMSki + url)
                            
                            #print routeKartverketHike + url

    if lastCalc:
        for batchiter in batch(urls, 100):
            batchURL = []
            print "Batch: ",
            for item in batchiter:
                batchURL.append(item)

            """if len(urls) < 250:
                rs = (grequests.get(u) for u in urls)
                print "Antall beregninger i batch: ", len(urls)
                results = grequests.map(rs)
            else:
                rs = (grequests.get(u) for u in urls[0:250])
                print "Antall beregninger i batch: ", len(urls)
                results = grequests.map(rs)
            """
            rs = (grequests.get(u) for u in batchURL)
            print "Antall beregninger i batch: ", len(batchURL)
            results = grequests.map(rs)

            for r in results:
                
                if r.json()['status'] == 0:
                    instructions = r.json()['route_instructions']
                    geometry = r.json()['route_geometry']
                    checksum = r.json()['hint_data']['checksum']
                    checkSumHintStartCoordinate = r.json()['hint_data']['locations'][0]
                    checkSumHintViaPoint1 = r.json()['hint_data']['locations'][1]
                    startPointLat = r.json()['via_points'][0][0]
                    startPointLon = r.json()['via_points'][0][1]
                    viaPoint1Lat = r.json()['via_points'][1][0]
                    viaPoint1Lon = r.json()['via_points'][1][1]
                    viaPoint2Lat = r.json()['via_points'][2][0]
                    viaPoint2Lon = r.json()['via_points'][2][1]

                    
                    
                    # Get total distance of non ski track segment
                    nonSkiTrackLength = 0
                    for segment in instructions:
                        featureType = segment[1]
                        if featureType != "skiing":
                            nonSkiTrackLength = nonSkiTrackLength + segment[2]

                    


                    # # Sjekk at alle viapunkter er på skiløyper. Hvis ikke vil vi sannsynligvis
                    # # ikke ha med turen. 

                    # Only append route if there is not to many non ski track segments on route. 
                    routeSummary = r.json()['route_summary']
                    #print "Total distance: ", routeSummary['total_distance']
                    #print "Non skiing distance: " , nonSkiTrackLength
                    #print "Divided: ", float(nonSkiTrackLength) / float(routeSummary['total_distance'])
                    if float(nonSkiTrackLength) / float(routeSummary['total_distance']) < 1:
                        # Convert to coordinate tuples
                        coordinates = decode(geometry)
                        
                        # Convert to line
                        line = LineString(coordinates)
                        utm33Line = transform(project, line)
                        b = utm33Line.bounds

                        # Calculate area per line. 
                        # The larger area the more circular a route is
                        utm33LineBuffered = utm33Line.buffer(10)
                        routeArea = utm33LineBuffered.area
                        routeLength = utm33Line.length
                        routeAreaPerLength = routeArea/routeLength

                        # Convert line bbox to polygon
                        polygon = Polygon([ (b[0], b[1]) , (b[0], b[3]), (b[2], b[3]), (b[2], b[1]) ])

                        routeArray.append({"nonSki": str(float(nonSkiTrackLength) / float(routeSummary['total_distance'])) , "distance": utm33Line.length, "bboxArea": polygon.area, "lineArea": routeArea , "lineAreaPerLength": routeAreaPerLength ,  "startPoint": [startPointLat,startPointLon],"endPoint": [startPointLat,startPointLon],"viaPoint1": [viaPoint1Lat,viaPoint1Lon],"viaPoint2": [viaPoint2Lat,viaPoint2Lon]})
                    #else:
                    #    #print "TAR IKKE MED!"
                else:
                    print "Rute feila!"

    return routeArray


def orderRouteAlternatives(routeAlternativesArray, length):

    # Extract routes that is approxiamatly same length as requested
    correctLengthList = []
    maxLength = length*1000*1.2
    minLength = length*1000-length*1000*0.2
    print "maxLength: " , maxLength
    print "minLength: " , minLength
    for route in routeAlternativesArray:
        if route['distance'] > minLength and route['distance'] < maxLength:
            correctLengthList.append(route)
    routeAlternativesArray = correctLengthList

    # Remove duplicate bbox area
    # We consider these as the same route suggestion
    noDuplicatesList = []
    bboxAreaList = []
    for route in routeAlternativesArray:
        bboxAreaList.append(route['bboxArea'])

    for i in range(0, len(bboxAreaList)):
        if bboxAreaList[i] not in bboxAreaList[i+1:]:
            #print "append"
            noDuplicatesList.append(routeAlternativesArray[i])
        #else:
        #    print "remove"
    routeAlternativesArray = noDuplicatesList

    
    # Sort by bbox area
    # http://stackoverflow.com/questions/72899/how-do-i-sort-a-list-of-dictionaries-by-values-of-the-dictionary-in-python
    sortedByBboxArea = sorted(routeAlternativesArray, key=lambda k: k['lineAreaPerLength'])
    sortedByBboxArea.reverse()


    # Find non circular routes

    # Find route that do not cross each other
    # object.is_simple


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

#if __name__ == "__main__":
#    app.run()



