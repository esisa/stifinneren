stifinneren
===========


apt-get install python-shapely python-flask
pip install geojson requests grequests



Starte script:
nohup ./osrm-routed -c kartverket_tur.ini > /var/log/stifinneren/kartverket_tur.log &
nohup ./osrm-routed -c osm_ski.ini > /var/log/stifinneren/osm_ski.log &

Kjører i test:
kartverket_tur=8081 kartverket_tur.ini
osm_ski=8084 osm_ski.ini

Ikke laget:
kartverket_ski=8082 kartverket_ski.ini
osm_tur=8083 osm_tur.ini



kartverket 
osm

hiking
skiing
trolley

slow
normal
fast


Gåtur
Skitur
Barnevogntur

Barnevennlig
Mosjonist
Sprek
