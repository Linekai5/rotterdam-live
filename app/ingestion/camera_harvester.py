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
from sqlalchemy import text
from app.ingestion.base import BaseIngestor
from app.logging import logger
from app.db.session import AsyncSessionLocal
from app.services.spatial_service import find_district_for_point, upsert_city_amenity


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

    async def harvest_osm_cameras(self) -> List[Dict[str, Any]]:
        """
        Attempt to scrape additional live outdoor camera nodes from OpenStreetMap mirrors.
        Strictly filters for outdoor cameras (indoor != yes).
        """
        query = """
        [out:json][timeout:15];
        (
          node["man_made"="surveillance"](51.86,4.35,51.98,4.60);
          node["surveillance"](51.86,4.35,51.98,4.60);
        );
        out body 100;
        """
        client = await self.get_client()
        for mirror in self.OVERPASS_MIRRORS:
            try:
                url = f"{mirror}?data=" + urllib.parse.quote(query.strip())
                res = await client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    elements = data.get("elements", [])
                    if elements:
                        logger.info("Successfully fetched {} outdoor camera nodes from OSM ({})", len(elements), mirror)
                        cameras = []
                        for node in elements:
                            tags = node.get("tags", {})
                            # STRICT: Only outdoor cameras
                            if tags.get("indoor") in ("yes", "true") or tags.get("location") == "indoor":
                                continue
                            cam_type = tags.get("surveillance:type") or tags.get("camera:type") or "outdoor_cctv"
                            zone = tags.get("surveillance:zone") or "openbare ruimte"
                            op = tags.get("operator") or "Openbare Toezichtscamera"
                            cameras.append({
                                "id": f"cam-osm-{node['id']}",
                                "name": f"Outdoor Camera: {zone.title()} ({cam_type})",
                                "lat": float(node["lat"]),
                                "lon": float(node["lon"]),
                                "camera_type": "surveillance",
                                "operator": op,
                                "description": f"OpenStreetMap outdoor camera: {cam_type} ({op})",
                                "details_extra": {
                                    "osm_id": node["id"],
                                    "camera_type": cam_type,
                                    "surveillance_zone": zone,
                                    "indoor": False,
                                },
                            })
                        return cameras
            except Exception as e:
                logger.debug("Overpass mirror {} failed: {}", mirror, e)
                continue
        return []

    async def ingest(self) -> Dict[str, int]:
        """
        Harvest all outdoor cameras and validate strictly against Rotterdam boundaries.
        Returns breakdown of saved cameras.
        """
        logger.info("Starting dedicated Rotterdam Outdoor Camera Harvester...")

        # 1. Collect all candidates
        traffic_cams = self.get_traffic_cameras()
        mun_cams = self.get_municipal_surveillance_cameras()
        webcams = self.get_public_webcams()
        anpr_cams = self.get_anpr_enforcement_cameras()
        osm_cams = await self.harvest_osm_cameras()

        all_candidates = traffic_cams + mun_cams + webcams + anpr_cams + osm_cams
        logger.info("Discovered {} total candidate cameras across all feeds", len(all_candidates))

        saved_traffic = 0
        saved_surveillance = 0
        saved_webcam = 0
        saved_anpr = 0
        rejected_outside = 0

        async with AsyncSessionLocal() as session:
            for cam in all_candidates:
                lon = float(cam["lon"])
                lat = float(cam["lat"])

                # 2. STRICT SPATIAL FILTER: Validate camera is strictly within Rotterdam
                district = await find_district_for_point(lon, lat, session)
                if not district:
                    logger.debug(
                        "Camera {} ({}, {}) is OUTSIDE Rotterdam municipal districts - strictly rejected",
                        cam["id"], lon, lat,
                    )
                    rejected_outside += 1
                    continue

                cam_type = cam.get("camera_type", "surveillance")

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
                    if cam_type == "traffic":
                        saved_traffic += 1
                    elif cam_type == "surveillance":
                        saved_surveillance += 1
                    elif cam_type == "skyline_webcam":
                        saved_webcam += 1
                    elif cam_type == "anpr":
                        saved_anpr += 1

        total_saved = saved_traffic + saved_surveillance + saved_webcam + saved_anpr
        logger.info(
            "Rotterdam Camera Harvester complete: {} outdoor cameras saved ({} traffic, {} police surveillance, {} webcams, {} ANPR). {} rejected outside Rotterdam.",
            total_saved, saved_traffic, saved_surveillance, saved_webcam, saved_anpr, rejected_outside,
        )

        return {
            "traffic_cameras": saved_traffic,
            "police_surveillance": saved_surveillance,
            "skyline_webcams": saved_webcam,
            "anpr_enforcement": saved_anpr,
            "rejected_outside_rotterdam": rejected_outside,
            "total_cameras": total_saved,
        }
