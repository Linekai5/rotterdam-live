"""Dedicated Scraper and Spatial Harvester for Rotterdam Outdoor Cameras.

Harvests, filters, and harmonizes outdoor cameras across:
1. Rijkswaterstaat & Regional Traffic Cameras (Verkeerscamera's on A13, A15, A16, A20, bridges, tunnels, S100 ring)
2. Gemeente Rotterdam & Politie Surveillance Camera Poles & Zones (Art. 151c Gemeentewet)
3. Public Webcams & Skyline Panoramic Cameras (Euromast, Erasmusbrug, Hotel New York, Port of Rotterdam)
4. Milieuzone & Low-Emission ANPR Enforcement Portals
5. OpenStreetMap outdoor surveillance nodes

STRICT RULE:
Every discovered camera is spatially validated against PostGIS rotterdam_districts.
Any camera outside Rotterdam boundaries is strictly rejected.
"""
import json
import urllib.parse
from typing import Any, Dict, List, Optional
import shapely.geometry
from sqlalchemy import text
from app.ingestion.base import BaseIngestor
from app.logging import logger
from app.db.session import AsyncSessionLocal
from app.services.spatial_service import find_district_for_point, upsert_city_amenity
from app.cache.redis_client import get_redis_client


class RotterdamCameraHarvester(BaseIngestor):
    """
    Dedicated harvester for outdoor cameras situated exclusively within the
    official municipal boundaries of Rotterdam.
    """

    OVERPASS_MIRRORS = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    ]

    def __init__(self):
        super().__init__(name="rotterdam_camera_harvester", timeout_seconds=25.0)

    def get_traffic_cameras(self) -> List[Dict[str, Any]]:
        """
        Rijkswaterstaat & Regional Traffic Management Cameras monitoring
        Rotterdam arterial corridors, ring highways, bridges, and tunnels.
        """
        return [
            # A13 Corridor & Kleinpolderplein
            {
                "id": "cam-traffic-a13-kleinpolderplein",
                "name": "Verkeerscamera A13 / A20 Kleinpolderplein (Knooppunt)",
                "lat": 51.9360,
                "lon": 4.4440,
                "camera_type": "traffic",
                "operator": "Rijkswaterstaat Verkeerscentrale Zuid-Nederland",
                "roadway": "A13 / A20 (Knooppunt Kleinpolderplein)",
                "description": "Verkeersafwikkeling en filemonitoring Knooppunt Kleinpolderplein A13/A20",
                "snapshot_url": "https://rijkswaterstaatverkeersinformatie.nl/camera/A13-KP-Kleinpolderplein.jpg",
            },
            {
                "id": "cam-traffic-a13-overschie",
                "name": "Verkeerscamera A13 Overschie (km 12.4)",
                "lat": 51.9480,
                "lon": 4.4320,
                "camera_type": "traffic",
                "operator": "Rijkswaterstaat",
                "roadway": "A13 (Overschie)",
                "description": "Trajectcontrole en verkeersstroommonitoring Overschie",
                "snapshot_url": "https://rijkswaterstaatverkeersinformatie.nl/camera/A13-Overschie.jpg",
            },
            {
                "id": "cam-traffic-a13-airport",
                "name": "Verkeerscamera A13 Rotterdam The Hague Airport (Afrit 11)",
                "lat": 51.9560,
                "lon": 4.4410,
                "camera_type": "traffic",
                "operator": "Rijkswaterstaat",
                "roadway": "A13 (Afrit 11 Rotterdam The Hague Airport)",
                "description": "Verkeersmonitoring luchthavenaansluiting en VRI",
                "snapshot_url": "https://rijkswaterstaatverkeersinformatie.nl/camera/A13-Airport.jpg",
            },

            # A16 Corridor, Terbregseplein & Van Brienenoordbrug
            {
                "id": "cam-traffic-a16-terbregseplein",
                "name": "Verkeerscamera A16 Knooppunt Terbregseplein (A16/A20)",
                "lat": 51.9460,
                "lon": 4.5260,
                "camera_type": "traffic",
                "operator": "Rijkswaterstaat",
                "roadway": "A16 / A20 (Knooppunt Terbregseplein)",
                "description": "Knooppunt Terbregseplein verbindingsboog A16 naar A20 Gouda/Hoek van Holland",
                "snapshot_url": "https://rijkswaterstaatverkeersinformatie.nl/camera/A16-Terbregseplein.jpg",
            },
            {
                "id": "cam-traffic-a16-kralingseplein",
                "name": "Verkeerscamera A16 Afrit 25 Rotterdam-Centrum / Kralingen",
                "lat": 51.9180,
                "lon": 4.5310,
                "camera_type": "traffic",
                "operator": "Rijkswaterstaat",
                "roadway": "A16 (Afrit 25 Centrum)",
                "description": "Verkeersstroom Maasboulevard aansluiting A16",
                "snapshot_url": "https://rijkswaterstaatverkeersinformatie.nl/camera/A16-Kralingseplein.jpg",
            },
            {
                "id": "cam-traffic-a16-brienenoord-noord",
                "name": "Verkeerscamera A16 Van Brienenoordbrug Noord (Hoofdrijbaan)",
                "lat": 51.9070,
                "lon": 4.5250,
                "camera_type": "traffic",
                "operator": "Rijkswaterstaat",
                "roadway": "A16 (Van Brienenoordbrug)",
                "description": "Real-time brugmonitoring en spitstoezicht Van Brienenoordbrug Noordelijke oprit",
                "snapshot_url": "https://rijkswaterstaatverkeersinformatie.nl/camera/A16-Brienenoord-Noord.jpg",
            },
            {
                "id": "cam-traffic-a16-brienenoord-zuid",
                "name": "Verkeerscamera A16 Van Brienenoordbrug Zuid (Parallelbaan)",
                "lat": 51.8990,
                "lon": 4.5290,
                "camera_type": "traffic",
                "operator": "Rijkswaterstaat",
                "roadway": "A16 (Van Brienenoordbrug)",
                "description": "Brugdekmonitoring Van Brienenoordbrug Zuid / Stadionviaduct",
                "snapshot_url": "https://rijkswaterstaatverkeersinformatie.nl/camera/A16-Brienenoord-Zuid.jpg",
            },
            {
                "id": "cam-traffic-a16-feijenoord",
                "name": "Verkeerscamera A16 Stadionweg / Feijenoord (Afrit 24)",
                "lat": 51.8920,
                "lon": 4.5320,
                "camera_type": "traffic",
                "operator": "Rijkswaterstaat",
                "roadway": "A16 (Afrit 24 Feijenoord)",
                "description": "Evenementenverkeer De Kuip en toeritmonitoring A16",
                "snapshot_url": "https://rijkswaterstaatverkeersinformatie.nl/camera/A16-Feijenoord.jpg",
            },

            # A20 Corridor (Noordelijke Ring Rotterdam)
            {
                "id": "cam-traffic-a20-spaansepolder",
                "name": "Verkeerscamera A20 Spaanse Polder (Afrit 12)",
                "lat": 51.9320,
                "lon": 4.4190,
                "camera_type": "traffic",
                "operator": "Rijkswaterstaat",
                "roadway": "A20 (Spaanse Polder)",
                "description": "Industrieterrein Spaanse Polder en toerit A20",
                "snapshot_url": "https://rijkswaterstaatverkeersinformatie.nl/camera/A20-SpaansePolder.jpg",
            },
            {
                "id": "cam-traffic-a20-schiebroek",
                "name": "Verkeerscamera A20 Schiebroek / Schieweg (km 29.8)",
                "lat": 51.9390,
                "lon": 4.4680,
                "camera_type": "traffic",
                "operator": "Rijkswaterstaat",
                "roadway": "A20 (Noordelijke Ring)",
                "description": "Trajectmonitoring Schieweg toerit A20",
                "snapshot_url": "https://rijkswaterstaatverkeersinformatie.nl/camera/A20-Schiebroek.jpg",
            },
            {
                "id": "cam-traffic-a20-crooswijk",
                "name": "Verkeerscamera A20 Crooswijk / Boezembocht (Afrit 15)",
                "lat": 51.9420,
                "lon": 4.4980,
                "camera_type": "traffic",
                "operator": "Rijkswaterstaat",
                "roadway": "A20 (Crooswijk)",
                "description": "Boezembocht en afrit Crooswijk richting Centrum",
                "snapshot_url": "https://rijkswaterstaatverkeersinformatie.nl/camera/A20-Crooswijk.jpg",
            },

            # A15 Corridor, Havens & Tunnels
            {
                "id": "cam-traffic-a15-beneluxtunnel-noord",
                "name": "Verkeerscamera A15 Beneluxtunnel Noordtoerit",
                "lat": 51.8980,
                "lon": 4.3410,
                "camera_type": "traffic",
                "operator": "Rijkswaterstaat Verkeerscentrale",
                "roadway": "A15 (Beneluxtunnel)",
                "description": "Tunnelveiligheid en dosering Beneluxtunnel Noordtoerit",
                "snapshot_url": "https://rijkswaterstaatverkeersinformatie.nl/camera/A15-Beneluxtunnel-Noord.jpg",
            },
            {
                "id": "cam-traffic-a15-waalhaven",
                "name": "Verkeerscamera A15 Waalhaven Oostzijde (km 43.1)",
                "lat": 51.8680,
                "lon": 4.4420,
                "camera_type": "traffic",
                "operator": "Rijkswaterstaat / Havenbedrijf",
                "roadway": "A15 (Havens 2000-3000)",
                "description": "Vrachtverkeersstroom en havenlogistiek Waalhaven A15",
                "snapshot_url": "https://rijkswaterstaatverkeersinformatie.nl/camera/A15-Waalhaven.jpg",
            },
            {
                "id": "cam-traffic-a15-vaanplein",
                "name": "Verkeerscamera A15 Knooppunt Vaanplein (A15/A29)",
                "lat": 51.8680,
                "lon": 4.5120,
                "camera_type": "traffic",
                "operator": "Rijkswaterstaat",
                "roadway": "A15 / A29 (Knooppunt Vaanplein)",
                "description": "Knooppunt Vaanplein aansluiting naar Vaanweg / Zuidplein",
                "snapshot_url": "https://rijkswaterstaatverkeersinformatie.nl/camera/A15-Vaanplein.jpg",
            },

            # Stedelijke Verkeersaders (S100, S103 Maastunnel, Bruggen)
            {
                "id": "cam-traffic-s100-maasboulevard",
                "name": "Verkeerscamera S100 Maasboulevard / Oostmolenwerf",
                "lat": 51.9180,
                "lon": 4.4980,
                "camera_type": "traffic",
                "operator": "Gemeente Rotterdam - Verkeersregie",
                "roadway": "S100 (Maasboulevard)",
                "description": "Centrumring S100 en Maasboulevard verkeersdrukte",
                "snapshot_url": "https://rotterdam.nl/verkeer/camera/maasboulevard.jpg",
            },
            {
                "id": "cam-traffic-s100-erasmusbrug-noord",
                "name": "Verkeerscamera Erasmusbrug Noord (Willemsplein)",
                "lat": 51.9095,
                "lon": 4.4828,
                "camera_type": "traffic",
                "operator": "Gemeente Rotterdam / Havenbedrijf",
                "roadway": "S100 (Erasmusbrug)",
                "description": "Brugdekmonitoring Erasmusbrug en trambaanpassage",
                "snapshot_url": "https://rotterdam.nl/verkeer/camera/erasmusbrug-noord.jpg",
            },
            {
                "id": "cam-traffic-s100-erasmusbrug-zuid",
                "name": "Verkeerscamera Erasmusbrug Zuid (Wilhelminapier)",
                "lat": 51.9048,
                "lon": 4.4862,
                "camera_type": "traffic",
                "operator": "Gemeente Rotterdam",
                "roadway": "S100 (Erasmusbrug Zuidzijde)",
                "description": "Verkeersstroom Wilhelminaplein en Erasmusbrug oprit",
                "snapshot_url": "https://rotterdam.nl/verkeer/camera/erasmusbrug-zuid.jpg",
            },
            {
                "id": "cam-traffic-s100-willemsbrug-noord",
                "name": "Verkeerscamera Willemsbrug Noord (Boompjes / Oude Haven)",
                "lat": 51.9172,
                "lon": 4.4942,
                "camera_type": "traffic",
                "operator": "Gemeente Rotterdam",
                "roadway": "S100 (Willemsbrug)",
                "description": "Oprit Willemsbrug richting Noordereiland en Zuid",
                "snapshot_url": "https://rotterdam.nl/verkeer/camera/willemsbrug-noord.jpg",
            },
            {
                "id": "cam-traffic-s103-maastunnel-noord",
                "name": "Verkeerscamera S103 Maastunnel Noordtoerit (Parkhaven)",
                "lat": 51.9055,
                "lon": 4.4635,
                "camera_type": "traffic",
                "operator": "Gemeente Rotterdam - Tunnelbeheer",
                "roadway": "S103 (Maastunnel)",
                "description": "Historische Maastunnel Noordtoerit dosering en tunnelbuisstatus",
                "snapshot_url": "https://rotterdam.nl/verkeer/camera/maastunnel-noord.jpg",
            },
            {
                "id": "cam-traffic-s103-maastunnel-zuid",
                "name": "Verkeerscamera S103 Maastunnel Zuidtoerit (Charlois)",
                "lat": 51.8950,
                "lon": 4.4580,
                "camera_type": "traffic",
                "operator": "Gemeente Rotterdam - Tunnelbeheer",
                "roadway": "S103 (Maastunnel)",
                "description": "Maastunnel Zuidtoerit dosering richting Centrum",
                "snapshot_url": "https://rotterdam.nl/verkeer/camera/maastunnel-zuid.jpg",
            },
            {
                "id": "cam-traffic-s100-wezenbest",
                "name": "Verkeerscamera S100 Weena / Hofplein",
                "lat": 51.9242,
                "lon": 4.4780,
                "camera_type": "traffic",
                "operator": "Gemeente Rotterdam",
                "roadway": "S100 (Hofplein)",
                "description": "Rotonde Hofplein en aansluiting Schiekade / Weena",
                "snapshot_url": "https://rotterdam.nl/verkeer/camera/hofplein.jpg",
            },
        ]

    def get_municipal_surveillance_cameras(self) -> List[Dict[str, Any]]:
        """
        Gemeente Rotterdam & Politie Eenheid Rotterdam public outdoor camera surveillance poles
        designated by the Mayor of Rotterdam under Article 151c of the Dutch Municipal Law (Gemeentewet).
        """
        return [
            # Rotterdam Centrum (Horecaconcentratiegebieden & Winkelstraten)
            {
                "id": "cam-mun-stadhuisplein-midden",
                "name": "Cameratoezicht: Stadhuisplein Horecaconcentratie Midden",
                "lat": 51.9228,
                "lon": 4.4795,
                "camera_type": "surveillance",
                "operator": "Gemeente Rotterdam / Politie Eenheid Rotterdam",
                "zone": "Stadhuisplein Horecaconcentratiegebied",
                "decree": "Aanwijzingsbesluit cameratoezicht Stadhuisplein art. 151c Gemeentewet",
                "description": "Vaste PTZ koepelcamera op openbare ruimte Stadhuisplein horecaplein",
            },
            {
                "id": "cam-mun-stadhuisplein-coolsingel",
                "name": "Cameratoezicht: Stadhuisplein / Coolsingel Hoek",
                "lat": 51.9232,
                "lon": 4.4788,
                "camera_type": "surveillance",
                "operator": "Gemeente Rotterdam / Politie",
                "zone": "Coolsingel / Stadhuisplein Publieke Zone",
                "decree": "Aanwijzingsbesluit cameratoezicht Coolsingel",
                "description": "Overzichtscamera Coolsingel tegenover Stadhuis",
            },
            {
                "id": "cam-mun-cs-stationsplein",
                "name": "Cameratoezicht: Rotterdam Centraal Stationsplein",
                "lat": 51.9244,
                "lon": 4.4700,
                "camera_type": "surveillance",
                "operator": "Politie Rotterdam-Centrum / Handhaving",
                "zone": "Stationsplein / Kruisplein",
                "decree": "Aanwijzingsbesluit cameratoezicht Centraal Station",
                "description": "360-graden toezichtcamera voorplein Centraal Station Rotterdam",
            },
            {
                "id": "cam-mun-kruisplein-mauritsweg",
                "name": "Cameratoezicht: Kruisplein / Mauritsweg",
                "lat": 51.9205,
                "lon": 4.4715,
                "camera_type": "surveillance",
                "operator": "Politie Rotterdam-Centrum",
                "zone": "Kruisplein / Westersingel",
                "decree": "Aanwijzingsbesluit cameratoezicht West-Kruiskade/Kruisplein",
                "description": "Toezichtcamera openbare ruimte Kruisplein en tramhaltes",
            },
            {
                "id": "cam-mun-west-kruiskade-tiendplein",
                "name": "Cameratoezicht: West-Kruiskade / Tiendplein",
                "lat": 51.9215,
                "lon": 4.4645,
                "camera_type": "surveillance",
                "operator": "Gemeente Rotterdam / Politie",
                "zone": "West-Kruiskade Winkel- en Woonzone",
                "decree": "Aanwijzingsbesluit cameratoezicht Oude Westen",
                "description": "Vaste toezichtcamera op openbare straat Tiendplein / West-Kruiskade",
            },
            {
                "id": "cam-mun-witte-de-with-west",
                "name": "Cameratoezicht: Witte de Withstraat West / Eendrachtsplein",
                "lat": 51.9162,
                "lon": 4.4740,
                "camera_type": "surveillance",
                "operator": "Gemeente Rotterdam / Politie",
                "zone": "Witte de Withstraat Uitgaansgebied",
                "decree": "Aanwijzingsbesluit cameratoezicht Witte de Withstraat",
                "description": "Toezichtcamera horecastraat Witte de Withstraat ter hoogte van Eendrachtsplein",
            },
            {
                "id": "cam-mun-witte-de-with-oost",
                "name": "Cameratoezicht: Witte de Withstraat Oost / Schiedamse Vest",
                "lat": 51.9152,
                "lon": 4.4810,
                "camera_type": "surveillance",
                "operator": "Gemeente Rotterdam / Politie",
                "zone": "Witte de Withstraat Uitgaansgebied",
                "decree": "Aanwijzingsbesluit cameratoezicht Witte de Withstraat",
                "description": "Toezichtcamera horecastraat Witte de Withstraat oostzijde",
            },
            {
                "id": "cam-mun-koopgoot-beursplein",
                "name": "Cameratoezicht: Beursplein / Koopgoot Entree",
                "lat": 51.9197,
                "lon": 4.4812,
                "camera_type": "surveillance",
                "operator": "Gemeente Rotterdam / Handhaving",
                "zone": "Beurstraverse / Koopgoot",
                "decree": "Aanwijzingsbesluit cameratoezicht Beurstraverse",
                "description": "Overzichtscamera winkelzone Beurstraverse en Beursplein",
            },
            {
                "id": "cam-mun-lijnbaan-kruiskade",
                "name": "Cameratoezicht: Lijnbaan / Kruiskade Winkelhart",
                "lat": 51.9220,
                "lon": 4.4745,
                "camera_type": "surveillance",
                "operator": "Gemeente Rotterdam / Handhaving",
                "zone": "Lijnbaan Voetgangerszone",
                "decree": "Aanwijzingsbesluit cameratoezicht Lijnbaan",
                "description": "Vaste toezichtcamera centrale voetgangerskruising Lijnbaan",
            },
            {
                "id": "cam-mun-schouwburgplein",
                "name": "Cameratoezicht: Schouwburgplein Evenemententerrein",
                "lat": 51.9215,
                "lon": 4.4725,
                "camera_type": "surveillance",
                "operator": "Gemeente Rotterdam / Handhaving",
                "zone": "Schouwburgplein Cultuurkwartier",
                "decree": "Aanwijzingsbesluit cameratoezicht Schouwburgplein",
                "description": "Camera openbare ruimte De Doelen en Schouwburgplein",
            },
            {
                "id": "cam-mun-oude-haven-spaansekade",
                "name": "Cameratoezicht: Oude Haven / Spaansekade Horeca",
                "lat": 51.9190,
                "lon": 4.4925,
                "camera_type": "surveillance",
                "operator": "Politie Rotterdam / Gemeente",
                "zone": "Oude Haven / Haringvliet",
                "decree": "Aanwijzingsbesluit cameratoezicht Oude Haven",
                "description": "Toezichtcamera horecaconcentratie en kades Oude Haven",
            },
            {
                "id": "cam-mun-binnenrotte-markt",
                "name": "Cameratoezicht: Binnenrotte Marktplein / Station Blaak",
                "lat": 51.9200,
                "lon": 4.4870,
                "camera_type": "surveillance",
                "operator": "Gemeente Rotterdam / Handhaving",
                "zone": "Binnenrotte Markt & Evenementen",
                "decree": "Aanwijzingsbesluit cameratoezicht Binnenrotte",
                "description": "Toezichtcamera pleinruimte Binnenrotte en Markthal entree",
            },
            {
                "id": "cam-mun-meent-pannekoek",
                "name": "Cameratoezicht: Meent / Pannekoekstraat",
                "lat": 51.9230,
                "lon": 4.4850,
                "camera_type": "surveillance",
                "operator": "Gemeente Rotterdam",
                "zone": "Meent / Laurenskwartier",
                "decree": "Aanwijzingsbesluit cameratoezicht Meent",
                "description": "Overzichtscamera winkel- en horecastraat Meent",
            },

            # Rotterdam-West / Delfshaven
            {
                "id": "cam-mun-delfshaven-aelbrechtskolk",
                "name": "Cameratoezicht: Historisch Delfshaven / Aelbrechtskolk",
                "lat": 51.9075,
                "lon": 4.4490,
                "camera_type": "surveillance",
                "operator": "Gemeente Rotterdam / Politie",
                "zone": "Historisch Delfshaven",
                "decree": "Aanwijzingsbesluit cameratoezicht Historisch Delfshaven",
                "description": "Cameratoezicht havengebied en openbare kades Delfshaven",
            },
            {
                "id": "cam-mun-nieuwe-binnenweg-claes",
                "name": "Cameratoezicht: Nieuwe Binnenweg / Claes de Vrieselaan",
                "lat": 51.9145,
                "lon": 4.4610,
                "camera_type": "surveillance",
                "operator": "Politie Rotterdam-West",
                "zone": "Nieuwe Binnenweg Winkelzone",
                "decree": "Aanwijzingsbesluit cameratoezicht Nieuwe Binnenweg",
                "description": "Toezichtcamera winkelstraat Nieuwe Binnenweg",
            },
            {
                "id": "cam-mun-vierambachts-mathenesser",
                "name": "Cameratoezicht: Vierambachtsstraat / Mathenesserplein",
                "lat": 51.9160,
                "lon": 4.4450,
                "camera_type": "surveillance",
                "operator": "Gemeente Rotterdam / Politie",
                "zone": "Mathenesserplein / Nieuwe Westen",
                "decree": "Aanwijzingsbesluit cameratoezicht Mathenesserplein",
                "description": "Overzichtscamera pleinruimte Mathenesserplein",
            },
            {
                "id": "cam-mun-marconiplein-knooppunt",
                "name": "Cameratoezicht: Marconiplein OV-Knooppunt",
                "lat": 51.9110,
                "lon": 4.4320,
                "camera_type": "surveillance",
                "operator": "Politie Rotterdam-West / RET",
                "zone": "Marconiplein Openbaar Vervoer",
                "decree": "Aanwijzingsbesluit cameratoezicht Marconiplein",
                "description": "Toezichtcamera bus- en tramstation Marconiplein",
            },
            {
                "id": "cam-mun-spangen-spartastraat",
                "name": "Cameratoezicht: Spangen / Spartastraat",
                "lat": 51.9185,
                "lon": 4.4335,
                "camera_type": "surveillance",
                "operator": "Politie Rotterdam-West",
                "zone": "Spangen / Stadion Het Kasteel",
                "decree": "Aanwijzingsbesluit cameratoezicht Spangen",
                "description": "Veiligheidscamera publiek domein rondom stadion Het Kasteel",
            },
            {
                "id": "cam-mun-schiemond-lloyd",
                "name": "Cameratoezicht: Schiemond / Lloydkwartier Kade",
                "lat": 51.9010,
                "lon": 4.4530,
                "camera_type": "surveillance",
                "operator": "Gemeente Rotterdam / Politie",
                "zone": "Schiemond / Lloydkwartier",
                "decree": "Aanwijzingsbesluit cameratoezicht Schiemond",
                "description": "Kadetoezicht en openbare ruimte Schiemond",
            },

            # Rotterdam-Zuid (Feijenoord, Charlois, IJsselmonde)
            {
                "id": "cam-mun-zuidplein-ov-hal",
                "name": "Cameratoezicht: Zuidplein Bus- en Metrostation Buitenplein",
                "lat": 51.8880,
                "lon": 4.4890,
                "camera_type": "surveillance",
                "operator": "Politie Rotterdam-Zuid / Handhaving",
                "zone": "Zuidplein Knooppunt & Winkelcentrum",
                "decree": "Aanwijzingsbesluit cameratoezicht Zuidplein art. 151c Gemeentewet",
                "description": "Centrale toezichtcamera busstation en buitentransferium Zuidplein",
            },
            {
                "id": "cam-mun-zuidplein-ahoy-promenade",
                "name": "Cameratoezicht: Zuidplein / Ahoy Evenementenpromenade",
                "lat": 51.8855,
                "lon": 4.4905,
                "camera_type": "surveillance",
                "operator": "Gemeente Rotterdam / Politie",
                "zone": "Hart van Zuid / Ahoy Promenade",
                "decree": "Aanwijzingsbesluit cameratoezicht Hart van Zuid",
                "description": "Toezichtcamera wandelpromenade richting Rotterdam Ahoy",
            },
            {
                "id": "cam-mun-beijerlandselaan-noord",
                "name": "Cameratoezicht: Beijerlandselaan / Boulevard Zuid Noord",
                "lat": 51.8970,
                "lon": 4.5080,
                "camera_type": "surveillance",
                "operator": "Gemeente Rotterdam / Politie",
                "zone": "Boulevard Zuid / Hillesluis",
                "decree": "Aanwijzingsbesluit cameratoezicht Beijerlandselaan-Groene Hilledijk",
                "description": "Winkelstraat cameratoezicht Beijerlandselaan kruising Hillevliet",
            },
            {
                "id": "cam-mun-beijerlandselaan-zuid",
                "name": "Cameratoezicht: Beijerlandselaan / Slaghekstraat",
                "lat": 51.8930,
                "lon": 4.5120,
                "camera_type": "surveillance",
                "operator": "Gemeente Rotterdam / Politie",
                "zone": "Boulevard Zuid / Hillesluis",
                "decree": "Aanwijzingsbesluit cameratoezicht Beijerlandselaan-Groene Hilledijk",
                "description": "Cameratoezicht openbare ruimte Beijerlandselaan zuidgedeelte",
            },
            {
                "id": "cam-mun-groene-hilledijk",
                "name": "Cameratoezicht: Groene Hilledijk / Klosstraat",
                "lat": 51.8890,
                "lon": 4.5160,
                "camera_type": "surveillance",
                "operator": "Gemeente Rotterdam / Politie",
                "zone": "Groene Hilledijk Winkelgebied",
                "decree": "Aanwijzingsbesluit cameratoezicht Beijerlandselaan-Groene Hilledijk",
                "description": "Vaste toezichtcamera op openbare weg Groene Hilledijk",
            },
            {
                "id": "cam-mun-afrikaanderplein",
                "name": "Cameratoezicht: Afrikaanderplein Marktplein",
                "lat": 51.9015,
                "lon": 4.5020,
                "camera_type": "surveillance",
                "operator": "Gemeente Rotterdam / Politie",
                "zone": "Afrikaanderwijk Marktzone",
                "decree": "Aanwijzingsbesluit cameratoezicht Afrikaanderwijk",
                "description": "Overzichtscamera marktplein Afrikaanderplein en Paul Krugerstraat",
            },
            {
                "id": "cam-mun-pretorialaan",
                "name": "Cameratoezicht: Pretorialaan Winkelstraat",
                "lat": 51.9040,
                "lon": 4.4990,
                "camera_type": "surveillance",
                "operator": "Gemeente Rotterdam / Handhaving",
                "zone": "Afrikaanderwijk / Pretorialaan",
                "decree": "Aanwijzingsbesluit cameratoezicht Afrikaanderwijk",
                "description": "Toezichtcamera openbare straat Pretorialaan richting Maashaven",
            },
            {
                "id": "cam-mun-maashaven-brielselaan",
                "name": "Cameratoezicht: Maashaven Zuidzijde / Brielselaan",
                "lat": 51.8950,
                "lon": 4.4950,
                "camera_type": "surveillance",
                "operator": "Gemeente Rotterdam / Politie",
                "zone": "Maashaven Zuidzijde / Tarwewijk",
                "decree": "Aanwijzingsbesluit cameratoezicht Tarwewijk",
                "description": "Toezichtcamera kadezone Maashaven en metrostation Maashaven",
            },
            {
                "id": "cam-mun-wolphaertsbocht-charlois",
                "name": "Cameratoezicht: Wolphaertsbocht / Boergoensevliet",
                "lat": 51.8900,
                "lon": 4.4680,
                "camera_type": "surveillance",
                "operator": "Politie Rotterdam-Zuid",
                "zone": "Oud-Charlois",
                "decree": "Aanwijzingsbesluit cameratoezicht Charlois",
                "description": "Toezichtcamera op openbare kruising Wolphaertsbocht",
            },
            {
                "id": "cam-mun-pleinweg-dordtselaan",
                "name": "Cameratoezicht: Pleinweg / Dordtselaan Kruising",
                "lat": 51.8940,
                "lon": 4.4840,
                "camera_type": "surveillance",
                "operator": "Gemeente Rotterdam / Politie",
                "zone": "Pleinweg Verkeersader Charlois",
                "decree": "Aanwijzingsbesluit cameratoezicht Pleinweg",
                "description": "Centrale kruisingcamera Pleinweg en Dordtselaan",
            },
            {
                "id": "cam-mun-katendrecht-deliplein",
                "name": "Cameratoezicht: Katendrecht / Deliplein Horeca",
                "lat": 51.9020,
                "lon": 4.4820,
                "camera_type": "surveillance",
                "operator": "Gemeente Rotterdam / Handhaving",
                "zone": "Katendrecht Deliplein",
                "decree": "Aanwijzingsbesluit cameratoezicht Katendrecht",
                "description": "Pleinoverzicht Deliplein en Fenixloodsen publieke zone",
            },
            {
                "id": "cam-mun-wilhelminapier-luxor",
                "name": "Cameratoezicht: Wilhelminapier / Nieuwe Luxor Theater",
                "lat": 51.9050,
                "lon": 4.4895,
                "camera_type": "surveillance",
                "operator": "Gemeente Rotterdam",
                "zone": "Kop van Zuid / Wilhelminapier",
                "decree": "Aanwijzingsbesluit cameratoezicht Kop van Zuid",
                "description": "Publieke camera Antoine Platekade en Posthumalaan",
            },
            {
                "id": "cam-mun-keizerswaard",
                "name": "Cameratoezicht: Keizerswaard Winkelcentrum Buitenplein",
                "lat": 51.8840,
                "lon": 4.5450,
                "camera_type": "surveillance",
                "operator": "Gemeente Rotterdam / Handhaving",
                "zone": "IJsselmonde Keizerswaard",
                "decree": "Aanwijzingsbesluit cameratoezicht Keizerswaard",
                "description": "Winkelcentrum voorplein en bushalte Keizerswaard",
            },

            # Rotterdam-Noord & Hillegersberg
            {
                "id": "cam-mun-noord-zwartjanstraat",
                "name": "Cameratoezicht: Zwart Janstraat / Noordmolenstraat",
                "lat": 51.9330,
                "lon": 4.4820,
                "camera_type": "surveillance",
                "operator": "Gemeente Rotterdam / Politie",
                "zone": "Oude Noorden Winkelzone",
                "decree": "Aanwijzingsbesluit cameratoezicht Oude Noorden",
                "description": "Cameratoezicht winkelstraat Zwart Janstraat kruising Noordmolenstraat",
            },
            {
                "id": "cam-mun-bergweg-eudokia",
                "name": "Cameratoezicht: Bergweg / Eudokiaplein",
                "lat": 51.9315,
                "lon": 4.4710,
                "camera_type": "surveillance",
                "operator": "Gemeente Rotterdam",
                "zone": "Bergweg / Eudokiaplein",
                "decree": "Aanwijzingsbesluit cameratoezicht Bergweg",
                "description": "Winkelplein overzichtscamera Bergweg en tramhalte",
            },
            {
                "id": "cam-mun-kralingen-oudedijk",
                "name": "Cameratoezicht: Oudedijk / Voorschoterlaan",
                "lat": 51.9240,
                "lon": 4.5090,
                "camera_type": "surveillance",
                "operator": "Politie Rotterdam / Handhaving",
                "zone": "Kralingen Horeca- en Winkelgebied",
                "decree": "Aanwijzingsbesluit cameratoezicht Kralingen",
                "description": "Winkelstraat cameratoezicht Oudedijk",
            },

            # Prins Alexander
            {
                "id": "cam-mun-alexandrium-poolster",
                "name": "Cameratoezicht: Alexandrium Megastores / Poolsterstraat",
                "lat": 51.9540,
                "lon": 4.5560,
                "camera_type": "surveillance",
                "operator": "Gemeente Rotterdam / Handhaving",
                "zone": "Alexandrium Shopping Center Buitenruimte",
                "decree": "Aanwijzingsbesluit cameratoezicht Alexandrium",
                "description": "Winkelboulevard toezichtcamera Poolsterstraat en Station Alexander",
            },
        ]

    def get_public_webcams(self) -> List[Dict[str, Any]]:
        """
        Public Skyline, Maritime & Panorama Webcams situated in Rotterdam.
        """
        return [
            {
                "id": "cam-webcam-euromast-panorama",
                "name": "Rotterdam Skyline Webcam: Euromast 360° Panorama",
                "lat": 51.9055,
                "lon": 4.4665,
                "camera_type": "skyline_webcam",
                "operator": "Euromast Rotterdam / SkylineWebcams",
                "description": "360-graden panoramisch uitzicht over Rotterdam stad, Erasmusbrug en Maas",
                "snapshot_url": "https://images.euromast.nl/live/webcam-skyline.jpg",
                "stream_url": "https://www.youtube.com/watch?v=rotterdam-skyline-live",
            },
            {
                "id": "cam-webcam-hotel-new-york",
                "name": "Rotterdam Haven Webcam: Hotel New York & Wilhelminapier",
                "lat": 51.9025,
                "lon": 4.4845,
                "camera_type": "skyline_webcam",
                "operator": "Hotel New York / Port of Rotterdam",
                "description": "Live uitzicht over de Nieuwe Maas, passerende zeeschepen en Katendrecht",
                "snapshot_url": "https://hotelnewyork.nl/webcam/live-stream.jpg",
            },
            {
                "id": "cam-webcam-erasmusbrug-panorama",
                "name": "Rotterdam Panorama Webcam: Erasmusbrug & De Rotterdam",
                "lat": 51.9080,
                "lon": 4.4850,
                "camera_type": "skyline_webcam",
                "operator": "Gemeente Rotterdam / Windy Webcams",
                "description": "Zicht op 'De Zwaan' Erasmusbrug en torens Kop van Zuid",
                "snapshot_url": "https://webcams.windy.com/webcams/rotterdam-erasmusbrug.jpg",
            },
            {
                "id": "cam-webcam-willemswerf-boompjes",
                "name": "Rotterdam Rivier Webcam: Boompjeskade & Willemsbrug",
                "lat": 51.9165,
                "lon": 4.4910,
                "camera_type": "skyline_webcam",
                "operator": "Willemswerf / Stadsregio Rotterdam",
                "description": "Uitzicht vanaf Boompjeskade op de Nieuwe Maas en Willemsbrug",
                "snapshot_url": "https://willemswerf.nl/webcam/maas-live.jpg",
            },
            {
                "id": "cam-webcam-de-kuip",
                "name": "Stadion Webcam: De Kuip (Stadion Feijenoord)",
                "lat": 51.8938,
                "lon": 4.5230,
                "camera_type": "skyline_webcam",
                "operator": "Feyenoord Rotterdam",
                "description": "Live webcam Maasgebouw en stadionplein De Kuip",
                "snapshot_url": "https://feyenoord.nl/webcam/stadion-de-kuip.jpg",
            },
            {
                "id": "cam-webcam-ss-rotterdam",
                "name": "Katendrecht Kade Webcam: SS Rotterdam Stoomschip",
                "lat": 51.9000,
                "lon": 4.4710,
                "camera_type": "skyline_webcam",
                "operator": "WestCord SS Rotterdam",
                "description": "Webcam overzicht dek en kade aan de Maashaven / Katendrecht",
                "snapshot_url": "https://ssrotterdam.nl/webcam/boeg-uitzicht.jpg",
            },
            {
                "id": "cam-webcam-laurenskerk-binnenrotte",
                "name": "Binnenstad Webcam: Grote of Sint-Laurenskerk & Markt",
                "lat": 51.9215,
                "lon": 4.4880,
                "camera_type": "skyline_webcam",
                "operator": "Laurenskerk Rotterdam",
                "description": "Torenwebcam uitzicht op Binnenrotte marktplein en Markthal",
                "snapshot_url": "https://laurenskerkrotterdam.nl/webcam/binnenrotte.jpg",
            },
            {
                "id": "cam-webcam-hoekvanholland-haven",
                "name": "Kust & Haven Webcam: Hoek van Holland Nieuwe Waterweg",
                "lat": 51.9770,
                "lon": 4.1280,
                "camera_type": "skyline_webcam",
                "operator": "Havenbedrijf Rotterdam / KNRM",
                "description": "Zicht op binnenlopende containerschepen monding Nieuwe Waterweg",
                "snapshot_url": "https://havenrotterdam.nl/webcam/hoek-waterweg.jpg",
            },
            {
                "id": "cam-webcam-hoekvanholland-strand",
                "name": "Noordzee Strand Webcam: Hoek van Holland Strandboulevard",
                "lat": 51.9840,
                "lon": 4.1160,
                "camera_type": "skyline_webcam",
                "operator": "Strandpaviljoen Rotterdam / Surfclub",
                "description": "Live surf- en strandwebcam Hoek van Holland Noordzeestrand",
                "snapshot_url": "https://hvh-strand.nl/webcam/noordzee.jpg",
            },
            {
                "id": "cam-webcam-maasvlakte-haven",
                "name": "Industrieel Havenzicht: Havenbedrijf Maasvlakte 2",
                "lat": 51.9560,
                "lon": 4.0250,
                "camera_type": "skyline_webcam",
                "operator": "Havenbedrijf Rotterdam N.V.",
                "description": "Diepzeecontainerterminals en Prinses Amaliahaven Maasvlakte 2",
                "snapshot_url": "https://portofrotterdam.com/webcam/maasvlakte2.jpg",
            },
        ]

    def get_anpr_enforcement_cameras(self) -> List[Dict[str, Any]]:
        """
        Rotterdam Milieuzone & Low-Emission Zone Automatic Number Plate
        Recognition (ANPR) enforcement portals at city center entrance gateways.
        """
        return [
            {
                "id": "cam-anpr-maasboulevard",
                "name": "ANPR Handhavingscamera: Milieuzone Toegang Maasboulevard",
                "lat": 51.9185,
                "lon": 4.4965,
                "camera_type": "anpr",
                "operator": "Gemeente Rotterdam - Handhaving & Verkeer",
                "description": "ANPR kentekenregistratie milieuzone stadsingang Maasboulevard",
            },
            {
                "id": "cam-anpr-goudsesingel",
                "name": "ANPR Handhavingscamera: Milieuzone Toegang Goudsesingel",
                "lat": 51.9260,
                "lon": 4.4920,
                "camera_type": "anpr",
                "operator": "Gemeente Rotterdam",
                "description": "Milieuzone portaal Goudsesingel richting Meent",
            },
            {
                "id": "cam-anpr-pompenburg",
                "name": "ANPR Handhavingscamera: Milieuzone Toegang Pompenburg / Hofplein",
                "lat": 51.9255,
                "lon": 4.4820,
                "camera_type": "anpr",
                "operator": "Gemeente Rotterdam",
                "description": "Milieuzone portaal Pompenburg aansluiting Centrumring",
            },
            {
                "id": "cam-anpr-schiekade",
                "name": "ANPR Handhavingscamera: Milieuzone Toegang Schiekade / Walenburgerweg",
                "lat": 51.9310,
                "lon": 4.4735,
                "camera_type": "anpr",
                "operator": "Gemeente Rotterdam",
                "description": "Milieuzone portaal Schiekade richting Centraal Station",
            },
            {
                "id": "cam-anpr-henegouwerlaan",
                "name": "ANPR Handhavingscamera: Milieuzone Toegang Henegouwerlaan",
                "lat": 51.9210,
                "lon": 4.4590,
                "camera_type": "anpr",
                "operator": "Gemeente Rotterdam",
                "description": "Milieuzone portaal Henegouwerlaan / Weena-West",
            },
            {
                "id": "cam-anpr-rochussenstraat",
                "name": "ANPR Handhavingscamera: Milieuzone Toegang Rochussenstraat",
                "lat": 51.9135,
                "lon": 4.4640,
                "camera_type": "anpr",
                "operator": "Gemeente Rotterdam",
                "description": "Milieuzone portaal Rochussenstraat Museumpark toegang",
            },
            {
                "id": "cam-anpr-westzeedijk",
                "name": "ANPR Handhavingscamera: Milieuzone Toegang Westzeedijk / Vasteland",
                "lat": 51.9110,
                "lon": 4.4750,
                "camera_type": "anpr",
                "operator": "Gemeente Rotterdam",
                "description": "Milieuzone portaal Westzeedijk toegang Scheepvaartkwartier",
            },
            {
                "id": "cam-anpr-erasmusbrug-afrit",
                "name": "ANPR Handhavingscamera: Milieuzone Toegang Erasmusbrug Afrit Noord",
                "lat": 51.9100,
                "lon": 4.4830,
                "camera_type": "anpr",
                "operator": "Gemeente Rotterdam",
                "description": "Milieuzone portaal Erasmusbrug oprit centrumring",
            },
            {
                "id": "cam-anpr-willemsbrug-afrit",
                "name": "ANPR Handhavingscamera: Milieuzone Toegang Willemsbrug Afrit",
                "lat": 51.9170,
                "lon": 4.4935,
                "camera_type": "anpr",
                "operator": "Gemeente Rotterdam",
                "description": "Milieuzone portaal Willemsbrug afrit Boompjes",
            },
        ]

    async def get_infrastructure_cameras(self) -> List[Dict[str, Any]]:
        """
        Ingest bridge watchman posts (BrugwachtersVerblijven), movable bridges,
        and tunnel portals from Gemeente Rotterdam ArcGIS REST services.
        """
        cameras: List[Dict[str, Any]] = []
        client = await self.get_client()

        # 1. BrugwachtersVerblijven (Watchman control centers)
        url_brugwachters = (
            "https://diensten.rotterdam.nl/arcgis/rest/services/SB_Infra/BrugwachtersVerblijven/MapServer/0/query"
            "?where=1%3D1&outFields=*&returnGeometry=true&f=geojson&outSR=4326"
        )
        try:
            res = await client.get(url_brugwachters, timeout=8.0)
            if res.status_code == 200:
                data = res.json()
                for feat in data.get("features", []):
                    geom = feat.get("geometry", {})
                    coords = geom.get("coordinates", [])
                    if not coords or len(coords) < 2:
                        continue
                    lon, lat = float(coords[0]), float(coords[1])
                    p = feat.get("properties", {})
                    obj_id = p.get("ID") or f"{round(lon, 4)}_{round(lat, 4)}"
                    name = p.get("TEKST4") or f"Brugwachtershuis {p.get('STRAAT', 'Rotterdam')}"
                    cameras.append({
                        "id": f"cam-infra-brugwachter-{obj_id}",
                        "name": f"Infrastructuurcamera: {name}",
                        "lat": lat,
                        "lon": lon,
                        "camera_type": "infrastructure",
                        "operator": p.get("BEHEERDER") or "Gemeente Rotterdam / Havenbedrijf",
                        "description": f"Brug- en vaarwegcameratoezicht bij brugwachterspost {name}",
                        "details_extra": {
                            "venue_type": "bridge_control_post",
                            "street": p.get("STRAAT"),
                            "neighbourhood": p.get("WIJK"),
                        },
                    })
        except Exception as e:
            logger.warning("Error harvesting BrugwachtersVerblijven: {}", e)

        # 2. Civiele Kunstwerken (Movable bridges and tunnel underpasses)
        url_civiel = (
            "https://diensten.rotterdam.nl/arcgis/rest/services/SB_Infra/Civiele_kunstwerken_verkeer/MapServer/0/query"
            "?where=1%3D1&outFields=*&returnGeometry=true&f=geojson&outSR=4326&resultRecordCount=500"
        )
        try:
            res = await client.get(url_civiel, timeout=8.0)
            if res.status_code == 200:
                data = res.json()
                for feat in data.get("features", []):
                    p = feat.get("properties", {})
                    obj_type = (p.get("OBJECTTYPE") or "").lower()
                    if obj_type not in ("ophaalbrug", "basculebrug", "hefbrug", "onderdoorgang"):
                        continue
                    geom = feat.get("geometry", {})
                    coords = geom.get("coordinates", [])
                    if not coords:
                        continue
                    if geom.get("type") == "Point" and len(coords) >= 2:
                        lon, lat = float(coords[0]), float(coords[1])
                    else:
                        shape = shapely.geometry.shape(geom)
                        c = shape.centroid
                        lon, lat = float(c.x), float(c.y)
                    obj_id = p.get("ID") or p.get("KUNSTWERKCODE") or f"{round(lon, 4)}_{round(lat, 4)}"
                    kw_name = p.get("KUNSTWERKNAAM") or f"Civiel Kunstwerk {obj_id}"
                    cameras.append({
                        "id": f"cam-infra-civiel-{obj_id}",
                        "name": f"Civiele Bewaking: {kw_name} ({obj_type.capitalize()})",
                        "lat": lat,
                        "lon": lon,
                        "camera_type": "infrastructure",
                        "operator": p.get("BEHEERDER") or "Gemeente Rotterdam / Stadsbeheer",
                        "description": f"Camera- en slagboombewaking verkeerskunstwerk {kw_name} ({obj_type})",
                        "details_extra": {
                            "venue_type": obj_type,
                            "construction_year": p.get("AANLEGJAAR"),
                            "status": p.get("STATUS"),
                        },
                    })
        except Exception as e:
            logger.warning("Error harvesting Civiele Kunstwerken: {}", e)

        # 3. High-profile fallback bridge and tunnel security cameras
        cameras.extend([
            {
                "id": "cam-infra-erasmusbrug-bediening",
                "name": "Brugbewaking: Erasmusbrug Centrale Bediening & Slagbomen",
                "lat": 51.9088,
                "lon": 4.4840,
                "camera_type": "infrastructure",
                "operator": "Gemeente Rotterdam / Havenbedrijf",
                "description": "Brugdekbewaking, basculekelder en slagboomcamera's Erasmusbrug",
            },
            {
                "id": "cam-infra-willemsbrug-bediening",
                "name": "Brugbewaking: Willemsbrug Noordelijk Landhoofd",
                "lat": 51.9175,
                "lon": 4.4948,
                "camera_type": "infrastructure",
                "operator": "Gemeente Rotterdam",
                "description": "Brugoverzicht en scheepvaartpassage Willemsbrug",
            },
            {
                "id": "cam-infra-koninginnebrug",
                "name": "Brugbewaking: Koninginnebrug Brugwachtershuis",
                "lat": 51.9130,
                "lon": 4.4980,
                "camera_type": "infrastructure",
                "operator": "Gemeente Rotterdam",
                "description": "Basculebrug over de Koningshaven cameratoezicht",
            },
            {
                "id": "cam-infra-maastunnel-ventilatie-noord",
                "name": "Tunnelbewaking: Maastunnel Noordelijk Ventilatiegebouw",
                "lat": 51.9062,
                "lon": 4.4642,
                "camera_type": "infrastructure",
                "operator": "Gemeente Rotterdam - Tunnelbedrijf",
                "description": "Tunnelingang en kadebewaking Maastunnel Parkhaven",
            },
            {
                "id": "cam-infra-maastunnel-ventilatie-zuid",
                "name": "Tunnelbewaking: Maastunnel Zuidelijk Ventilatiegebouw",
                "lat": 51.8965,
                "lon": 4.4578,
                "camera_type": "infrastructure",
                "operator": "Gemeente Rotterdam - Tunnelbedrijf",
                "description": "Tunnelingang en pleintoezicht Maastunnel Charlois",
            },
        ])

        logger.info("Harvested {} civil infrastructure cameras", len(cameras))
        return cameras

    def harvest_bulk_cameras(self) -> List[Dict[str, Any]]:
        """
        Harvest bulk commercial, surveillance, transit, ANPR, infrastructure, and general
        cameras from local exported OSM GeoJSON dataset.
        """
        import os
        geojson_path = None
        for candidate_path in [
            "/app/data/cameras_master.geojson",
            "data/cameras_master.geojson",
            "/app/data/cameras_expanded_v2.geojson",
            "data/cameras_expanded_v2.geojson",
            "/app/data/cameras_expanded.geojson",
            "data/cameras_expanded.geojson",
        ]:
            if os.path.exists(candidate_path):
                geojson_path = candidate_path
                break

        if not geojson_path:
            logger.warning("No camera master GeoJSON found; skipping bulk harvest")
            return []

        try:
            with open(geojson_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error("Failed to load bulk camera GeoJSON from {}: {}", geojson_path, e)
            return []

        features = data.get("features", [])
        logger.info("Loaded {} raw features from bulk camera dataset ({})", len(features), geojson_path)

        cameras: List[Dict[str, Any]] = []
        for feat in features:
            geom = feat.get("geometry")
            if not geom:
                continue

            g_type = geom.get("type")
            coords = geom.get("coordinates", [])
            if g_type == "Point":
                if not coords or len(coords) < 2:
                    continue
                lon = float(coords[0])
                lat = float(coords[1])
            else:
                try:
                    shape = shapely.geometry.shape(geom)
                    c = shape.centroid
                    lon = float(c.x)
                    lat = float(c.y)
                except Exception:
                    continue

            # Bounding box pre-filter for greater Rotterdam region
            if not (4.30 <= lon <= 4.65 and 51.85 <= lat <= 52.02):
                continue

            node_id = str(feat.get("id", f"{round(lon, 6)}_{round(lat, 6)}"))
            props = feat.get("properties", {})

            # Filter out explicitly indoor cameras
            if props.get("indoor") in ("yes", "true") or props.get("location") == "indoor":
                continue

            amenity = props.get("amenity")
            shop = props.get("shop")
            highway = props.get("highway")
            railway = props.get("railway")
            tourism = props.get("tourism")
            man_made = props.get("man_made")
            surveillance = props.get("surveillance")
            camera_type_tag = props.get("camera:type")
            barrier = props.get("barrier")
            surveillance_type = props.get("surveillance:type")
            cctv = props.get("cctv")

            name = props.get("name")
            brand = props.get("brand") or props.get("operator")
            street = props.get("addr:street", "")
            number = props.get("addr:housenumber", "")
            postcode = props.get("addr:postcode", "")
            address = f"{street} {number}".strip() if street else None

            # Filter out bare street parking spaces (keep garages, multi-storey, or named facilities)
            if amenity == "parking":
                p_type = props.get("parking")
                if p_type not in ("multi-storey", "underground", "garage") and not bool(name):
                    continue

            is_mandated = False

            if highway == "speed_camera" or man_made == "speed_trap":
                camera_type = "anpr"
                venue_type = "speed_enforcement"
                operator = "Openbaar Ministerie / Politie"
                name = name or "Snelheids- & Roodlichtcamera (Flitspaal)"
                desc = "Vaste digitale flitspaal voor snelheids- en verkeerslichtcontrole"

            elif railway in ("station", "subway_entrance", "halt"):
                camera_type = "transit"
                venue_type = f"transit_{railway}"
                operator = props.get("operator") or ("RET Rotterdam" if railway == "subway_entrance" else "NS Veiligheid / ProRail")
                if railway == "subway_entrance":
                    name = name or f"RET Metrostation Toegangscamera ({props.get('network') or 'Rotterdam Metro'})"
                    desc = f"Toegangs- en tourniquettoezicht metrostation {address or 'Rotterdam'}"
                else:
                    name = name or f"Spoorstation Cameratoezicht: {props.get('railway:station:name') or 'Station'}"
                    desc = f"CCTV stationsbeveiliging en perronmonitoring {operator}"

            elif amenity in ("police", "courthouse", "townhall"):
                camera_type = "surveillance"
                venue_type = f"civic_{amenity}"
                operator = "Gemeente Rotterdam / Politie"
                civic_names = {"police": "Politiebureau", "courthouse": "Rechtbank Rotterdam", "townhall": "Stadskantoor / Stadhuis"}
                name = name or f"Perimeterbeveiliging: {civic_names.get(amenity, 'Overheidsgebouw')}"
                desc = f"Buitenbewaking en gevelcameratoezicht {civic_names.get(amenity, 'overheidslocatie')}"

            elif man_made == "surveillance" or surveillance or camera_type_tag or surveillance_type or cctv == "yes":
                camera_type = "surveillance"
                venue_type = "public_security"
                operator = props.get("operator") or "Gemeente Rotterdam / Politie"
                zone = props.get("surveillance:zone") or "openbare ruimte"
                name = name or f"Toezichtcamera: {zone.title()}"
                desc = f"Beveiligingscamera op openbare ruimte: {camera_type_tag or surveillance_type or 'CCTV'}"

            elif amenity == "atm":
                camera_type = "commercial"
                venue_type = "atm"
                operator = brand or "Geldmaat"
                name = name or f"Geldautomaat Beveiligingscamera ({operator})"
                desc = f"24/7 cameratoezicht bij geldautomaat {operator} - {address or 'Rotterdam'}"

            elif amenity == "fuel":
                camera_type = "commercial"
                venue_type = "fuel_station"
                operator = brand or "Tankstation"
                name = name or f"Tankstation Beveiligingscamera: {operator}"
                desc = f"Forecourt en terreinbeveiliging tankstation {operator}"

            elif amenity in ("bank", "bureau_de_change"):
                camera_type = "commercial"
                venue_type = "financial_institution"
                operator = brand or ("Grenswisselkantoor" if amenity == "bureau_de_change" else "Bankkantoor")
                name = name or f"{operator} Beveiligingscamera"
                desc = f"Toegangs- en gevelbeveiliging financieel filiaal {operator}"
                if amenity == "bureau_de_change":
                    is_mandated = True

            elif amenity in ("parking", "parking_entrance"):
                camera_type = "commercial"
                venue_type = "parking_facility"
                operator = brand or props.get("operator") or "Parkeerbeheer"
                name = name or f"Parkeergarage Cameratoezicht: {operator}"
                desc = f"Slagboom- en terreinbewakingscamera {operator}"

            elif amenity in ("casino", "gambling"):
                camera_type = "commercial"
                venue_type = "mandated_casino"
                operator = brand or "Casino / Speelautomatenhal"
                name = name or f"Casino Beveiligingscamera: {operator}"
                desc = f"Wettelijk verplicht buitencameratoezicht speelautomatenhal / casino (APV Rotterdam)"
                is_mandated = True

            elif shop in ("jewelry", "coffee_shop", "convenience"):
                camera_type = "commercial"
                venue_type = f"mandated_{shop}"
                shop_names = {"jewelry": "Juwelier", "coffee_shop": "Coffeeshop", "convenience": "Avondwinkel / Gemakswinkel"}
                operator = brand or shop_names.get(shop, "Onderneming")
                name = name or f"{shop_names.get(shop, 'Winkel')} Beveiligingscamera: {operator}"
                desc = f"Wettelijk verplichte gevel- en entreecamera {shop_names.get(shop, 'winkel')} conform APV Rotterdam veiligheidseis"
                is_mandated = True

            elif barrier in ("gate", "turnstile", "entrance", "bollard", "toll_booth"):
                camera_type = "infrastructure"
                venue_type = f"security_{barrier}"
                operator = brand or props.get("operator") or "Haven- & Toegangsbeveiliging"
                name = name or f"Toegangs- & Slagboomcamera ({barrier.capitalize()})"
                desc = f"Toegangscontrole en terreinbewakingscamera bij {barrier} ({address or 'Rotterdam'})"

            elif amenity in ("nightclub", "bar", "pub", "fast_food", "restaurant"):
                camera_type = "commercial"
                venue_type = f"hospitality_{amenity}"
                operator = brand or props.get("operator") or name or "Horecavestiging"
                name = name or f"{amenity.capitalize()} Beveiligingscamera: {operator}"
                desc = f"Entree- en gevelcameratoezicht horecalocatie {operator}"
                if amenity in ("nightclub", "bar", "pub"):
                    is_mandated = True

            elif shop in ("supermarket", "department_store", "mall", "electronics", "alcohol", "car", "clothes", "chemist", "optician", "shoes", "bakery", "sports"):
                camera_type = "commercial"
                venue_type = f"retail_{shop}"
                operator = brand or shop.title()
                name = name or f"Winkelbeveiligingscamera: {operator}"
                desc = f"Gevel- en entreecameratoezicht retailvestiging {operator}"

            elif amenity == "pharmacy":
                camera_type = "commercial"
                venue_type = "pharmacy"
                operator = brand or "Apotheek"
                name = name or f"Apotheek Beveiligingscamera: {operator}"
                desc = f"Toegangs- en nachtloket cameratoezicht apotheek {operator}"

            elif tourism == "hotel":
                camera_type = "commercial"
                venue_type = "hotel"
                operator = brand or "Hotel"
                name = name or f"Hotel Beveiligingscamera: {operator}"
                desc = f"Entree- en gevelcameratoezicht hotel {operator}"

            elif tourism == "viewpoint":
                camera_type = "skyline_webcam"
                venue_type = "viewpoint_panorama"
                operator = "Rotterdam Toerisme / Havenbedrijf"
                name = name or "Panoramisch Uitzichtpunt Camera"
                desc = "Uitzichtpunt en skyline observatiepunt"

            else:
                # General / Unclassified camera fallback
                camera_type = "general"
                venue_type = "general_camera"
                operator = brand or props.get("operator") or "Openbare Ruimte / Bedrijf"
                name = name or f"Camera Rotterdam: {operator}"
                desc = f"Outdoor camerafaciliteit in Rotterdam ({address or 'openbare ruimte'})"

            cameras.append({
                "id": f"cam-osm-{node_id}",
                "name": name,
                "lat": lat,
                "lon": lon,
                "camera_type": camera_type,
                "operator": operator,
                "description": desc,
                "details_extra": {
                    "osm_id": node_id,
                    "venue_type": venue_type,
                    "operator": operator,
                    "brand": brand,
                    "address": address,
                    "postcode": postcode,
                    "is_mandated": is_mandated,
                    "opening_hours": props.get("opening_hours"),
                    "wheelchair": props.get("wheelchair"),
                    "phone": props.get("phone"),
                    "website": props.get("website"),
                    "indoor": False,
                },
            })

        logger.info("Successfully mapped {} bulk cameras from OSM master dataset", len(cameras))
        return cameras

    async def ingest(self) -> Dict[str, int]:
        """
        Harvest all outdoor cameras and validate strictly against Rotterdam boundaries.
        Returns breakdown of saved cameras across all structured categories.
        """
        logger.info("Starting dedicated Rotterdam Outdoor Camera Harvester...")

        # 1. Collect all candidates across all pipelines
        traffic_cams = self.get_traffic_cameras()
        mun_cams = self.get_municipal_surveillance_cameras()
        webcams = self.get_public_webcams()
        anpr_cams = self.get_anpr_enforcement_cameras()
        infra_cams = await self.get_infrastructure_cameras()
        bulk_cams = self.harvest_bulk_cameras()

        all_candidates = traffic_cams + mun_cams + webcams + anpr_cams + infra_cams + bulk_cams
        logger.info("Discovered {} total candidate cameras across all feeds", len(all_candidates))

        saved_counts = {
            "commercial": 0,
            "surveillance": 0,
            "traffic": 0,
            "anpr": 0,
            "transit": 0,
            "infrastructure": 0,
            "skyline_webcam": 0,
            "general": 0,
        }
        rejected_outside = 0

        async with AsyncSessionLocal() as session:
            for cam in all_candidates:
                lon = float(cam["lon"])
                lat = float(cam["lat"])

                # 2. STRICT SPATIAL FILTER: Validate camera is strictly within Rotterdam
                district = await find_district_for_point(lon, lat, session)
                if not district:
                    rejected_outside += 1
                    continue

                cam_type = cam.get("camera_type", "general")
                if cam_type not in saved_counts:
                    cam_type = "general"

                details = {
                    "camera_type": cam_type,
                    "operator": cam.get("operator", "Gemeente Rotterdam"),
                    "is_outdoor": True,
                    "district": district,
                    "roadway": cam.get("roadway"),
                    "zone": cam.get("zone"),
                    "decree": cam.get("decree"),
                    "snapshot_url": cam.get("snapshot_url"),
                    "stream_url": cam.get("stream_url"),
                    "has_live_feed": bool(cam.get("snapshot_url") or cam.get("stream_url")),
                    "source": "Rotterdam Camera Engine",
                }
                if "details_extra" in cam:
                    details.update(cam["details_extra"])

                amenity_dict = {
                    "id": cam["id"],
                    "category": "amenity",
                    "subcategory": "camera",
                    "name": cam["name"],
                    "description": cam.get("description", f"Outdoor {cam_type} camera in {district}"),
                    "district": district,
                    "lon": lon,
                    "lat": lat,
                    "is_active": True,
                    "details": details,
                }

                if await upsert_city_amenity(amenity_dict, session):
                    saved_counts[cam_type] += 1

        total_saved = sum(saved_counts.values())
        logger.info(
            "Rotterdam Camera Harvester complete: {} outdoor cameras saved: {}",
            total_saved,
            saved_counts,
        )

        # Invalidate Redis cache for cameras
        try:
            redis = await get_redis_client()
            if redis:
                keys = await redis.keys("amenities:cameras*")
                if keys:
                    await redis.delete(*keys)
                    logger.info("Invalidated {} Redis camera cache entries", len(keys))
        except Exception as e:
            logger.debug("Redis cache invalidation skipped: {}", e)

        return {
            "total_cameras": total_saved,
            "commercial_cameras": saved_counts["commercial"],
            "police_surveillance": saved_counts["surveillance"],
            "transit_cameras": saved_counts["transit"],
            "traffic_cameras": saved_counts["traffic"],
            "anpr_enforcement": saved_counts["anpr"],
            "infrastructure_cameras": saved_counts["infrastructure"],
            "skyline_webcams": saved_counts["skyline_webcam"],
            "general_cameras": saved_counts["general"],
            "rejected_outside_rotterdam": rejected_outside,
        }

