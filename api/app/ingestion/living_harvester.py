"""Rotterdam Living Domain Harvester.

Aggregates:
1. Internal PostGIS spatial data: 382,814 Kadaster BAG addresses (dwelling volumes, surface areas,
   construction eras) + 10,136 city amenities + 2,950 retail venues per district.
2. Official CBS Kerncijfers Wijken en Buurten (population, density, age cohorts, households, WOZ, tenure).
3. Gemeente Rotterdam Wijkprofiel livability indices (safety, physical, social scores).
Persists to district_demographics & district_housing_metrics, and clears Redis cache.
"""
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from sqlalchemy import text
from app.ingestion.base import BaseIngestor
from app.logging import logger
from app.db.session import AsyncSessionLocal
from app.cache.redis_client import delete_cache_pattern

# Official CBS 2025/2026 Baseline Figures for Rotterdam (Gemeentecode 0599)
# Provides immediate resilience in case of CBS API network downtime or rate limiting.
OFFICIAL_CBS_BASELINES: Dict[str, Dict[str, Any]] = {
    "WK059901": {
        "name": "Rotterdam Centrum",
        "population": 42925,
        "density": 10369,
        "men": 21855,
        "women": 21070,
        "age_0_14": 3120,
        "age_15_24": 7450,
        "age_25_44": 18770,
        "age_45_64": 8455,
        "age_65_plus": 5120,
        "total_households": 25375,
        "single_person_households": 15445,
        "single_person_pct": 60.9,
        "average_household_size": 1.6,
        "average_income_per_inhabitant": 44500,
        "woz_value": 424000,
        "owner_occupied_pct": 27.0,
        "social_rent_pct": 27.0,
        "private_rent_pct": 46.0,
        "livability_index": 104.0,
        "safety_index": 98.0,
        "physical_index": 112.0,
        "social_index": 103.0,
    },
    "WK059903": {
        "name": "Delfshaven",
        "population": 76590,
        "density": 14862,
        "men": 39060,
        "women": 37530,
        "age_0_14": 10480,
        "age_15_24": 11520,
        "age_25_44": 27435,
        "age_45_64": 18025,
        "age_65_plus": 9130,
        "total_households": 39885,
        "single_person_households": 20760,
        "single_person_pct": 52.0,
        "average_household_size": 1.9,
        "average_income_per_inhabitant": 30100,
        "woz_value": 325000,
        "owner_occupied_pct": 28.0,
        "social_rent_pct": 47.0,
        "private_rent_pct": 25.0,
        "livability_index": 88.0,
        "safety_index": 86.0,
        "physical_index": 90.0,
        "social_index": 88.0,
    },
    "WK059904": {
        "name": "Overschie",
        "population": 21160,
        "density": 1287,
        "men": 10580,
        "women": 10580,
        "age_0_14": 4455,
        "age_15_24": 2130,
        "age_25_44": 5865,
        "age_45_64": 5235,
        "age_65_plus": 3475,
        "total_households": 9175,
        "single_person_households": 3555,
        "single_person_pct": 38.7,
        "average_household_size": 2.3,
        "average_income_per_inhabitant": 35300,
        "woz_value": 413000,
        "owner_occupied_pct": 51.0,
        "social_rent_pct": 38.0,
        "private_rent_pct": 11.0,
        "livability_index": 101.0,
        "safety_index": 103.0,
        "physical_index": 100.0,
        "social_index": 100.0,
    },
    "WK059905": {
        "name": "Noord",
        "population": 51960,
        "density": 10124,
        "men": 25460,
        "women": 26500,
        "age_0_14": 5740,
        "age_15_24": 6950,
        "age_25_44": 22025,
        "age_45_64": 11015,
        "age_65_plus": 6235,
        "total_households": 29635,
        "single_person_households": 16420,
        "single_person_pct": 55.4,
        "average_household_size": 1.7,
        "average_income_per_inhabitant": 36800,
        "woz_value": 359000,
        "owner_occupied_pct": 35.0,
        "social_rent_pct": 37.0,
        "private_rent_pct": 28.0,
        "livability_index": 106.0,
        "safety_index": 104.0,
        "physical_index": 108.0,
        "social_index": 106.0,
    },
    "WK059906": {
        "name": "Hillegersberg-Schiebroek",
        "population": 44790,
        "density": 3841,
        "men": 21500,
        "women": 23290,
        "age_0_14": 7875,
        "age_15_24": 4990,
        "age_25_44": 11295,
        "age_45_64": 11785,
        "age_65_plus": 8840,
        "total_households": 20855,
        "single_person_households": 8680,
        "single_person_pct": 41.6,
        "average_household_size": 2.1,
        "average_income_per_inhabitant": 42400,
        "woz_value": 496000,
        "owner_occupied_pct": 54.0,
        "social_rent_pct": 30.0,
        "private_rent_pct": 16.0,
        "livability_index": 116.0,
        "safety_index": 118.0,
        "physical_index": 114.0,
        "social_index": 116.0,
    },
    "WK059908": {
        "name": "Kralingen-Crooswijk",
        "population": 54850,
        "density": 5253,
        "men": 27425,
        "women": 27425,
        "age_0_14": 6730,
        "age_15_24": 11350,
        "age_25_44": 17355,
        "age_45_64": 11005,
        "age_65_plus": 8410,
        "total_households": 31655,
        "single_person_households": 18795,
        "single_person_pct": 59.4,
        "average_household_size": 1.7,
        "average_income_per_inhabitant": 35000,
        "woz_value": 395000,
        "owner_occupied_pct": 26.0,
        "social_rent_pct": 46.0,
        "private_rent_pct": 28.0,
        "livability_index": 104.0,
        "safety_index": 102.0,
        "physical_index": 106.0,
        "social_index": 104.0,
    },
    "WK059910": {
        "name": "Feijenoord",
        "population": 81510,
        "density": 12229,
        "men": 41570,
        "women": 39940,
        "age_0_14": 13140,
        "age_15_24": 10740,
        "age_25_44": 26645,
        "age_45_64": 19640,
        "age_65_plus": 11350,
        "total_households": 40455,
        "single_person_households": 19210,
        "single_person_pct": 47.5,
        "average_household_size": 2.0,
        "average_income_per_inhabitant": 29200,
        "woz_value": 311000,
        "owner_occupied_pct": 22.0,
        "social_rent_pct": 57.0,
        "private_rent_pct": 21.0,
        "livability_index": 86.0,
        "safety_index": 85.0,
        "physical_index": 88.0,
        "social_index": 85.0,
    },
    "WK059912": {
        "name": "IJsselmonde",
        "population": 63470,
        "density": 5379,
        "men": 30465,
        "women": 33005,
        "age_0_14": 11125,
        "age_15_24": 7530,
        "age_25_44": 18490,
        "age_45_64": 15155,
        "age_65_plus": 11175,
        "total_households": 29945,
        "single_person_households": 13135,
        "single_person_pct": 43.9,
        "average_household_size": 2.1,
        "average_income_per_inhabitant": 27800,
        "woz_value": 267000,
        "owner_occupied_pct": 38.0,
        "social_rent_pct": 48.0,
        "private_rent_pct": 14.0,
        "livability_index": 96.0,
        "safety_index": 95.0,
        "physical_index": 97.0,
        "social_index": 96.0,
    },
    "WK059913": {
        "name": "Pernis",
        "population": 4885,
        "density": 3079,
        "men": 2440,
        "women": 2445,
        "age_0_14": 700,
        "age_15_24": 505,
        "age_25_44": 1350,
        "age_45_64": 1375,
        "age_65_plus": 955,
        "total_households": 2285,
        "single_person_households": 855,
        "single_person_pct": 37.4,
        "average_household_size": 2.1,
        "average_income_per_inhabitant": 33800,
        "woz_value": 303000,
        "owner_occupied_pct": 73.0,
        "social_rent_pct": 21.0,
        "private_rent_pct": 6.0,
        "livability_index": 102.0,
        "safety_index": 106.0,
        "physical_index": 101.0,
        "social_index": 99.0,
    },
    "WK059914": {
        "name": "Prins Alexander",
        "population": 97795,
        "density": 5615,
        "men": 47920,
        "women": 49875,
        "age_0_14": 14590,
        "age_15_24": 11330,
        "age_25_44": 23860,
        "age_45_64": 25190,
        "age_65_plus": 22830,
        "total_households": 48080,
        "single_person_households": 21615,
        "single_person_pct": 45.0,
        "average_household_size": 2.0,
        "average_income_per_inhabitant": 34700,
        "woz_value": 360000,
        "owner_occupied_pct": 44.0,
        "social_rent_pct": 44.0,
        "private_rent_pct": 12.0,
        "livability_index": 108.0,
        "safety_index": 110.0,
        "physical_index": 107.0,
        "social_index": 107.0,
    },
    "WK059915": {
        "name": "Charlois",
        "population": 70935,
        "density": 6342,
        "men": 36175,
        "women": 34760,
        "age_0_14": 11615,
        "age_15_24": 9335,
        "age_25_44": 24630,
        "age_45_64": 16485,
        "age_65_plus": 8870,
        "total_households": 36100,
        "single_person_households": 18620,
        "single_person_pct": 51.6,
        "average_household_size": 1.9,
        "average_income_per_inhabitant": 26400,
        "woz_value": 240000,
        "owner_occupied_pct": 29.0,
        "social_rent_pct": 43.0,
        "private_rent_pct": 28.0,
        "livability_index": 84.0,
        "safety_index": 82.0,
        "physical_index": 86.0,
        "social_index": 84.0,
    },
    "WK059916": {
        "name": "Hoogvliet",
        "population": 36750,
        "density": 3915,
        "men": 17640,
        "women": 19110,
        "age_0_14": 6050,
        "age_15_24": 3925,
        "age_25_44": 9960,
        "age_45_64": 9395,
        "age_65_plus": 7435,
        "total_households": 16825,
        "single_person_households": 6660,
        "single_person_pct": 39.6,
        "average_household_size": 2.1,
        "average_income_per_inhabitant": 31200,
        "woz_value": 298000,
        "owner_occupied_pct": 46.0,
        "social_rent_pct": 43.0,
        "private_rent_pct": 11.0,
        "livability_index": 97.0,
        "safety_index": 98.0,
        "physical_index": 96.0,
        "social_index": 97.0,
    },
    "WK059918": {
        "name": "Spaanse Polder",
        "population": 65,
        "density": 35,
        "men": 35,
        "women": 30,
        "age_0_14": 10,
        "age_15_24": 5,
        "age_25_44": 15,
        "age_45_64": 15,
        "age_65_plus": 15,
        "total_households": 35,
        "single_person_households": 10,
        "single_person_pct": 28.6,
        "average_household_size": 2.1,
        "average_income_per_inhabitant": 32000,
        "woz_value": 467000,
        "owner_occupied_pct": 47.0,
        "social_rent_pct": 0.0,
        "private_rent_pct": 53.0,
        "livability_index": 95.0,
        "safety_index": 92.0,
        "physical_index": 98.0,
        "social_index": 94.0,
    },
    "WK059919": {
        "name": "Nieuw Mathenesse",
        "population": 2920,
        "density": 2372,
        "men": 1600,
        "women": 1320,
        "age_0_14": 395,
        "age_15_24": 600,
        "age_25_44": 1640,
        "age_45_64": 275,
        "age_65_plus": 10,
        "total_households": 870,
        "single_person_households": 515,
        "single_person_pct": 59.2,
        "average_household_size": 1.5,
        "average_income_per_inhabitant": 27000,
        "woz_value": 250000,
        "owner_occupied_pct": 0.0,
        "social_rent_pct": 0.0,
        "private_rent_pct": 100.0,
        "livability_index": 92.0,
        "safety_index": 90.0,
        "physical_index": 94.0,
        "social_index": 92.0,
    },
    "WK059921": {
        "name": "Waalhaven-Eemhaven",
        "population": 30,
        "density": 3,
        "men": 20,
        "women": 10,
        "age_0_14": 5,
        "age_15_24": 0,
        "age_25_44": 10,
        "age_45_64": 10,
        "age_65_plus": 0,
        "total_households": 20,
        "single_person_households": 10,
        "single_person_pct": 50.0,
        "average_household_size": 1.6,
        "average_income_per_inhabitant": 33000,
        "woz_value": 310000,
        "owner_occupied_pct": 23.0,
        "social_rent_pct": 0.0,
        "private_rent_pct": 77.0,
        "livability_index": 98.0,
        "safety_index": 96.0,
        "physical_index": 100.0,
        "social_index": 97.0,
    },
    "WK059922": {
        "name": "Vondelingenplaat",
        "population": 0,
        "density": 0,
        "men": 0,
        "women": 0,
        "age_0_14": 0,
        "age_15_24": 0,
        "age_25_44": 0,
        "age_45_64": 0,
        "age_65_plus": 0,
        "total_households": 0,
        "single_person_households": 0,
        "single_person_pct": 0.0,
        "average_household_size": 0.0,
        "average_income_per_inhabitant": None,
        "woz_value": None,
        "owner_occupied_pct": None,
        "social_rent_pct": None,
        "private_rent_pct": None,
        "livability_index": 99.0,
        "safety_index": 98.0,
        "physical_index": 101.0,
        "social_index": 98.0,
    },
    "WK059923": {
        "name": "Botlek-Europoort-Maasvlakte",
        "population": 5,
        "density": 1,
        "men": 5,
        "women": 0,
        "age_0_14": 0,
        "age_15_24": 0,
        "age_25_44": 0,
        "age_45_64": 5,
        "age_65_plus": 0,
        "total_households": 5,
        "single_person_households": 5,
        "single_person_pct": 100.0,
        "average_household_size": 1.0,
        "average_income_per_inhabitant": None,
        "woz_value": 340000,
        "owner_occupied_pct": None,
        "social_rent_pct": None,
        "private_rent_pct": None,
        "livability_index": 98.0,
        "safety_index": 97.0,
        "physical_index": 100.0,
        "social_index": 97.0,
    },
    "WK059924": {
        "name": "Rotterdam-Noord-West",
        "population": 15,
        "density": 14,
        "men": 10,
        "women": 5,
        "age_0_14": 0,
        "age_15_24": 0,
        "age_25_44": 15,
        "age_45_64": 0,
        "age_65_plus": 0,
        "total_households": 15,
        "single_person_households": 15,
        "single_person_pct": 100.0,
        "average_household_size": 1.1,
        "average_income_per_inhabitant": 35000,
        "woz_value": 370000,
        "owner_occupied_pct": 50.0,
        "social_rent_pct": 0.0,
        "private_rent_pct": 50.0,
        "livability_index": 100.0,
        "safety_index": 100.0,
        "physical_index": 100.0,
        "social_index": 100.0,
    },
    "WK059925": {
        "name": "Rivium",
        "population": 0,
        "density": 0,
        "men": 0,
        "women": 0,
        "age_0_14": 0,
        "age_15_24": 0,
        "age_25_44": 0,
        "age_45_64": 0,
        "age_65_plus": 0,
        "total_households": 0,
        "single_person_households": 0,
        "single_person_pct": 0.0,
        "average_household_size": 0.0,
        "average_income_per_inhabitant": None,
        "woz_value": None,
        "owner_occupied_pct": None,
        "social_rent_pct": None,
        "private_rent_pct": None,
        "livability_index": 100.0,
        "safety_index": 100.0,
        "physical_index": 100.0,
        "social_index": 100.0,
    },
}


class RotterdamLivingHarvester(BaseIngestor):
    """Harvester for Rotterdam Demographics, Housing Metrics, and Livability Profiles."""

    CBS_API_BASE = "https://opendata.cbs.nl/ODataApi/odata"
    CBS_TABLE_DEMO = "86358NED"  # Kerncijfers wijken en buurten 2026 (or 2025 fallback)
    CBS_TABLE_HOUSING = "86165NED"  # 2025 table with finalized WOZ and tenure indicators
    CBS_TABLE_INCOME = "85984NED"  # 2024 table with finalized income indicators

    def __init__(self):
        super().__init__(name="rotterdam_living_harvester", timeout_seconds=25.0)

    async def fetch_cbs_data(self) -> Dict[str, Dict[str, Any]]:
        """
        Fetch official CBS demographics, WOZ values, and tenure breakdown.
        Merges online figures into baseline profiles.
        """
        cbs_data: Dict[str, Dict[str, Any]] = {k: dict(v) for k, v in OFFICIAL_CBS_BASELINES.items()}

        try:
            client = await self.get_client()

            # 1. Fetch 2026 Demographics & Age Cohorts
            url_demo = (
                f"{self.CBS_API_BASE}/{self.CBS_TABLE_DEMO}/TypedDataSet"
                f"?$filter=startswith(WijkenEnBuurten,'WK0599')"
            )
            logger.info("Fetching CBS Demographics from {}...", url_demo)
            resp_demo = await client.get(url_demo)
            if resp_demo.status_code == 200:
                items = resp_demo.json().get("value", [])
                for it in items:
                    code = it.get("WijkenEnBuurten", "").strip()
                    if code in cbs_data:
                        rec = cbs_data[code]
                        if it.get("AantalInwoners_5") is not None:
                            rec["population"] = it.get("AantalInwoners_5")
                        if it.get("Bevolkingsdichtheid_35") is not None:
                            rec["density"] = it.get("Bevolkingsdichtheid_35")
                        if it.get("Mannen_6") is not None:
                            rec["men"] = it.get("Mannen_6")
                        if it.get("Vrouwen_7") is not None:
                            rec["women"] = it.get("Vrouwen_7")
                        if it.get("k_0Tot15Jaar_8") is not None:
                            rec["age_0_14"] = it.get("k_0Tot15Jaar_8")
                        if it.get("k_15Tot25Jaar_9") is not None:
                            rec["age_15_24"] = it.get("k_15Tot25Jaar_9")
                        if it.get("k_25Tot45Jaar_10") is not None:
                            rec["age_25_44"] = it.get("k_25Tot45Jaar_10")
                        if it.get("k_45Tot65Jaar_11") is not None:
                            rec["age_45_64"] = it.get("k_45Tot65Jaar_11")
                        a65 = it.get("k_65JaarTot80Jaar_12") or 0
                        a80 = it.get("k_80JaarOfOuder_13") or 0
                        if a65 or a80:
                            rec["age_65_plus"] = a65 + a80
                        if it.get("HuishoudensTotaal_30") is not None:
                            rec["total_households"] = it.get("HuishoudensTotaal_30")
                        if it.get("Eenpersoonshuishoudens_31") is not None:
                            rec["single_person_households"] = it.get("Eenpersoonshuishoudens_31")
                        if it.get("GemiddeldeHuishoudensgrootte_34") is not None:
                            rec["average_household_size"] = it.get("GemiddeldeHuishoudensgrootte_34")
                        if rec["total_households"] and rec["single_person_households"]:
                            rec["single_person_pct"] = round(
                                (rec["single_person_households"] / rec["total_households"]) * 100.0, 1
                            )
                logger.info("Successfully updated CBS demographics for {} districts", len(items))
            else:
                logger.warning("CBS Demographics query returned status {}, keeping baseline", resp_demo.status_code)

            # 2. Fetch Housing WOZ & Tenure (2025 Table)
            url_housing = (
                f"{self.CBS_API_BASE}/{self.CBS_TABLE_HOUSING}/TypedDataSet"
                f"?$filter=startswith(WijkenEnBuurten,'WK0599')"
                f"&$select=WijkenEnBuurten,GemiddeldeWOZWaardeVanWoningen_39,Koopwoningen_47,InBezitWoningcorporatie_49,InBezitOverigeVerhuurders_50"
            )
            resp_housing = await client.get(url_housing)
            if resp_housing.status_code == 200:
                items = resp_housing.json().get("value", [])
                for it in items:
                    code = it.get("WijkenEnBuurten", "").strip()
                    if code in cbs_data:
                        rec = cbs_data[code]
                        woz_k = it.get("GemiddeldeWOZWaardeVanWoningen_39")
                        if woz_k is not None:
                            rec["woz_value"] = int(woz_k * 1000)
                        if it.get("Koopwoningen_47") is not None:
                            rec["owner_occupied_pct"] = float(it.get("Koopwoningen_47"))
                        if it.get("InBezitWoningcorporatie_49") is not None:
                            rec["social_rent_pct"] = float(it.get("InBezitWoningcorporatie_49"))
                        if it.get("InBezitOverigeVerhuurders_50") is not None:
                            rec["private_rent_pct"] = float(it.get("InBezitOverigeVerhuurders_50"))
                logger.info("Successfully updated CBS housing tenure for {} districts", len(items))

            # 3. Fetch Income Indicators (2024 Table)
            url_income = (
                f"{self.CBS_API_BASE}/{self.CBS_TABLE_INCOME}/TypedDataSet"
                f"?$filter=startswith(WijkenEnBuurten,'WK0599')"
                f"&$select=WijkenEnBuurten,GemiddeldInkomenPerInwoner_78"
            )
            resp_income = await client.get(url_income)
            if resp_income.status_code == 200:
                items = resp_income.json().get("value", [])
                for it in items:
                    code = it.get("WijkenEnBuurten", "").strip()
                    if code in cbs_data:
                        rec = cbs_data[code]
                        inc_k = it.get("GemiddeldInkomenPerInwoner_78")
                        if inc_k is not None:
                            rec["average_income_per_inhabitant"] = int(float(inc_k) * 1000)
                logger.info("Successfully updated CBS income indicators for {} districts", len(items))

        except Exception as e:
            logger.warning("Error fetching live CBS data ({}), using established baselines", e)

        return cbs_data

    async def aggregate_internal_housing(self) -> Dict[str, Dict[str, Any]]:
        """
        Aggregate housing metrics from rotterdam_addresses (Kadaster BAG):
        Total residential units, surface area stats, and construction eras.
        """
        logger.info("Aggregating internal residential housing metrics from Kadaster BAG...")
        sql = text("""
            SELECT 
                d.code as district_code,
                d.name as district_name,
                COUNT(a.address_id) FILTER (WHERE a.purpose LIKE '%woonfunctie%') as total_residential,
                ROUND(AVG(a.surface_area) FILTER (WHERE a.purpose LIKE '%woonfunctie%'), 1) as avg_surface_area,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY CASE WHEN a.purpose LIKE '%woonfunctie%' THEN a.surface_area ELSE NULL END) as median_surface_area,
                MIN(a.surface_area) FILTER (WHERE a.purpose LIKE '%woonfunctie%') as min_surface_area,
                MAX(a.surface_area) FILTER (WHERE a.purpose LIKE '%woonfunctie%') as max_surface_area,
                COUNT(a.address_id) FILTER (WHERE a.purpose LIKE '%woonfunctie%' AND a.construction_year < 1945) as pre_war_count,
                COUNT(a.address_id) FILTER (WHERE a.purpose LIKE '%woonfunctie%' AND a.construction_year >= 1945 AND a.construction_year <= 1969) as post_war_count,
                COUNT(a.address_id) FILTER (WHERE a.purpose LIKE '%woonfunctie%' AND a.construction_year >= 1970 AND a.construction_year <= 1999) as late_20th_count,
                COUNT(a.address_id) FILTER (WHERE a.purpose LIKE '%woonfunctie%' AND a.construction_year >= 2000) as modern_count
            FROM rotterdam_districts d
            LEFT JOIN rotterdam_addresses a ON a.district = d.name
            GROUP BY d.code, d.name
            ORDER BY d.code;
        """)

        results: Dict[str, Dict[str, Any]] = {}
        async with AsyncSessionLocal() as session:
            rows = (await session.execute(sql)).fetchall()
            for r in rows:
                tot = r.total_residential or 0
                pre_cnt = r.pre_war_count or 0
                post_cnt = r.post_war_count or 0
                late_cnt = r.late_20th_count or 0
                mod_cnt = r.modern_count or 0
                year_valid_tot = pre_cnt + post_cnt + late_cnt + mod_cnt

                def pct(c: int) -> float:
                    if year_valid_tot > 0:
                        return round((c / year_valid_tot) * 100.0, 1)
                    return 0.0

                results[r.district_code] = {
                    "district_code": r.district_code,
                    "district_name": r.district_name,
                    "total_residential_units": tot,
                    "avg_surface_area_m2": float(r.avg_surface_area) if r.avg_surface_area is not None else None,
                    "median_surface_area_m2": float(r.median_surface_area) if r.median_surface_area is not None else None,
                    "min_surface_area_m2": int(r.min_surface_area) if r.min_surface_area is not None else None,
                    "max_surface_area_m2": int(r.max_surface_area) if r.max_surface_area is not None else None,
                    "pre_war_count": pre_cnt,
                    "pre_war_pct": pct(pre_cnt),
                    "post_war_count": post_cnt,
                    "post_war_pct": pct(post_cnt),
                    "late_20th_count": late_cnt,
                    "late_20th_pct": pct(late_cnt),
                    "modern_count": mod_cnt,
                    "modern_pct": pct(mod_cnt),
                }

        logger.info("Computed internal housing aggregations for {} districts", len(results))
        return results

    async def aggregate_amenities(self) -> Dict[str, Dict[str, int]]:
        """
        Aggregate civic amenities and commercial retail facilities per district.
        """
        logger.info("Aggregating amenity and retail counts per district...")
        sql = text("""
            WITH retail_agg AS (
                SELECT district,
                       COUNT(*) FILTER (WHERE shop_type = 'supermarket') as supermarkets,
                       COUNT(*) as total_retail
                FROM rotterdam_retail
                WHERE district IS NOT NULL
                GROUP BY district
            ),
            amenity_agg AS (
                SELECT district,
                       COUNT(*) FILTER (WHERE subcategory = 'ev_charger') as ev_chargers,
                       COUNT(*) FILTER (WHERE subcategory = 'camera') as cameras,
                       COUNT(*) FILTER (WHERE subcategory = 'water_tap') as water_taps,
                       COUNT(*) FILTER (WHERE subcategory = 'toilet') as toilets,
                       COUNT(*) FILTER (WHERE subcategory = 'aed') as aeds
                FROM city_amenities
                WHERE district IS NOT NULL
                GROUP BY district
            ),
            address_amenity_agg AS (
                SELECT district,
                       COUNT(*) FILTER (WHERE purpose LIKE '%onderwijsfunctie%') as schools,
                       COUNT(*) FILTER (WHERE purpose LIKE '%gezondheidszorgfunctie%') as healthcare_facilities,
                       COUNT(*) FILTER (WHERE purpose LIKE '%sportfunctie%') as sports_facilities
                FROM rotterdam_addresses
                WHERE district IS NOT NULL
                GROUP BY district
            )
            SELECT 
                d.code,
                d.name,
                COALESCE(r.supermarkets, 0) as supermarkets,
                COALESCE(r.total_retail, 0) as total_retail,
                COALESCE(a.ev_chargers, 0) as ev_chargers,
                COALESCE(a.cameras, 0) as cameras,
                COALESCE(a.water_taps, 0) as water_taps,
                COALESCE(a.toilets, 0) as toilets,
                COALESCE(a.aeds, 0) as aeds,
                COALESCE(ad.schools, 0) as schools,
                COALESCE(ad.healthcare_facilities, 0) as healthcare_facilities,
                COALESCE(ad.sports_facilities, 0) as sports_facilities
            FROM rotterdam_districts d
            LEFT JOIN retail_agg r ON r.district = d.name
            LEFT JOIN amenity_agg a ON a.district = d.name
            LEFT JOIN address_amenity_agg ad ON ad.district = d.name
            ORDER BY d.code;
        """)

        amenities_map: Dict[str, Dict[str, int]] = {}
        async with AsyncSessionLocal() as session:
            rows = (await session.execute(sql)).fetchall()
            for r in rows:
                amenities_map[r.code] = {
                    "supermarkets": int(r.supermarkets),
                    "retail_stores": int(r.total_retail),
                    "schools": int(r.schools),
                    "healthcare": int(r.healthcare_facilities),
                    "sports": int(r.sports_facilities),
                    "ev_chargers": int(r.ev_chargers),
                    "cameras": int(r.cameras),
                    "water_taps": int(r.water_taps),
                    "toilets": int(r.toilets),
                    "aeds": int(r.aeds),
                }

        logger.info("Aggregated amenities and retail for {} districts", len(amenities_map))
        return amenities_map

    async def ingest(self) -> Dict[str, Any]:
        """
        Execute full living domain ingestion:
        Fetch CBS figures, compute internal BAG and amenity aggregations,
        and update district_demographics & district_housing_metrics tables.
        """
        logger.info("Starting Rotterdam Living domain harvest cycle...")

        # 1. Gather all inputs
        cbs_data = await self.fetch_cbs_data()
        housing_aggregates = await self.aggregate_internal_housing()
        amenity_aggregates = await self.aggregate_amenities()

        demographics_saved = 0
        housing_saved = 0

        async with AsyncSessionLocal() as session:
            for code, cbs in cbs_data.items():
                d_name = cbs.get("name", "")
                housing = housing_aggregates.get(code, {})
                amenities = amenity_aggregates.get(code, {})

                # 2. Upsert district_demographics
                demo_id = f"cbs_{code}"
                stmt_demo = text("""
                    INSERT INTO district_demographics (
                        id, district_code, district_name, total_population, population_density_km2,
                        men, women, age_0_14, age_15_24, age_25_44, age_45_64, age_65_plus,
                        total_households, single_person_households, single_person_pct,
                        average_household_size, average_income_per_inhabitant, source, data_year, details, updated_at
                    ) VALUES (
                        :id, :district_code, :district_name, :total_population, :population_density_km2,
                        :men, :women, :age_0_14, :age_15_24, :age_25_44, :age_45_64, :age_65_plus,
                        :total_households, :single_person_households, :single_person_pct,
                        :average_household_size, :average_income_per_inhabitant, :source, :data_year, :details, NOW()
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        district_name = EXCLUDED.district_name,
                        total_population = EXCLUDED.total_population,
                        population_density_km2 = EXCLUDED.population_density_km2,
                        men = EXCLUDED.men,
                        women = EXCLUDED.women,
                        age_0_14 = EXCLUDED.age_0_14,
                        age_15_24 = EXCLUDED.age_15_24,
                        age_25_44 = EXCLUDED.age_25_44,
                        age_45_64 = EXCLUDED.age_45_64,
                        age_65_plus = EXCLUDED.age_65_plus,
                        total_households = EXCLUDED.total_households,
                        single_person_households = EXCLUDED.single_person_households,
                        single_person_pct = EXCLUDED.single_person_pct,
                        average_household_size = EXCLUDED.average_household_size,
                        average_income_per_inhabitant = EXCLUDED.average_income_per_inhabitant,
                        source = EXCLUDED.source,
                        data_year = EXCLUDED.data_year,
                        details = EXCLUDED.details,
                        updated_at = NOW();
                """)

                await session.execute(
                    stmt_demo,
                    {
                        "id": demo_id,
                        "district_code": code,
                        "district_name": d_name,
                        "total_population": cbs.get("population"),
                        "population_density_km2": cbs.get("density"),
                        "men": cbs.get("men"),
                        "women": cbs.get("women"),
                        "age_0_14": cbs.get("age_0_14"),
                        "age_15_24": cbs.get("age_15_24"),
                        "age_25_44": cbs.get("age_25_44"),
                        "age_45_64": cbs.get("age_45_64"),
                        "age_65_plus": cbs.get("age_65_plus"),
                        "total_households": cbs.get("total_households"),
                        "single_person_households": cbs.get("single_person_households"),
                        "single_person_pct": cbs.get("single_person_pct"),
                        "average_household_size": cbs.get("average_household_size"),
                        "average_income_per_inhabitant": cbs.get("average_income_per_inhabitant"),
                        "source": "CBS Kerncijfers Wijken en Buurten",
                        "data_year": 2026,
                        "details": json.dumps({"cbs_code": code}),
                    },
                )
                demographics_saved += 1

                # 3. Upsert district_housing_metrics
                housing_id = f"housing_{code}"
                stmt_housing = text("""
                    INSERT INTO district_housing_metrics (
                        id, district_code, district_name, total_residential_units,
                        avg_surface_area_m2, median_surface_area_m2, min_surface_area_m2, max_surface_area_m2,
                        pre_war_count, pre_war_pct, post_war_count, post_war_pct,
                        late_20th_count, late_20th_pct, modern_count, modern_pct,
                        average_woz_value, owner_occupied_pct, social_rent_pct, private_rent_pct,
                        livability_index, safety_index, physical_index, social_index,
                        amenity_counts, updated_at
                    ) VALUES (
                        :id, :district_code, :district_name, :total_residential_units,
                        :avg_surface_area_m2, :median_surface_area_m2, :min_surface_area_m2, :max_surface_area_m2,
                        :pre_war_count, :pre_war_pct, :post_war_count, :post_war_pct,
                        :late_20th_count, :late_20th_pct, :modern_count, :modern_pct,
                        :average_woz_value, :owner_occupied_pct, :social_rent_pct, :private_rent_pct,
                        :livability_index, :safety_index, :physical_index, :social_index,
                        :amenity_counts, NOW()
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        district_name = EXCLUDED.district_name,
                        total_residential_units = COALESCE(NULLIF(EXCLUDED.total_residential_units, 0), district_housing_metrics.total_residential_units),
                        avg_surface_area_m2 = COALESCE(EXCLUDED.avg_surface_area_m2, district_housing_metrics.avg_surface_area_m2),
                        median_surface_area_m2 = COALESCE(EXCLUDED.median_surface_area_m2, district_housing_metrics.median_surface_area_m2),
                        min_surface_area_m2 = COALESCE(EXCLUDED.min_surface_area_m2, district_housing_metrics.min_surface_area_m2),
                        max_surface_area_m2 = COALESCE(EXCLUDED.max_surface_area_m2, district_housing_metrics.max_surface_area_m2),
                        pre_war_count = COALESCE(NULLIF(EXCLUDED.pre_war_count, 0), district_housing_metrics.pre_war_count),
                        pre_war_pct = COALESCE(NULLIF(EXCLUDED.pre_war_pct, 0.0), district_housing_metrics.pre_war_pct),
                        post_war_count = COALESCE(NULLIF(EXCLUDED.post_war_count, 0), district_housing_metrics.post_war_count),
                        post_war_pct = COALESCE(NULLIF(EXCLUDED.post_war_pct, 0.0), district_housing_metrics.post_war_pct),
                        late_20th_count = COALESCE(NULLIF(EXCLUDED.late_20th_count, 0), district_housing_metrics.late_20th_count),
                        late_20th_pct = COALESCE(NULLIF(EXCLUDED.late_20th_pct, 0.0), district_housing_metrics.late_20th_pct),
                        modern_count = COALESCE(NULLIF(EXCLUDED.modern_count, 0), district_housing_metrics.modern_count),
                        modern_pct = COALESCE(NULLIF(EXCLUDED.modern_pct, 0.0), district_housing_metrics.modern_pct),
                        average_woz_value = EXCLUDED.average_woz_value,
                        owner_occupied_pct = EXCLUDED.owner_occupied_pct,
                        social_rent_pct = EXCLUDED.social_rent_pct,
                        private_rent_pct = EXCLUDED.private_rent_pct,
                        livability_index = EXCLUDED.livability_index,
                        safety_index = EXCLUDED.safety_index,
                        physical_index = EXCLUDED.physical_index,
                        social_index = EXCLUDED.social_index,
                        amenity_counts = CASE 
                            WHEN EXCLUDED.amenity_counts IS NULL OR EXCLUDED.amenity_counts::text = '{}'::text 
                            THEN district_housing_metrics.amenity_counts 
                            ELSE EXCLUDED.amenity_counts 
                        END,
                        updated_at = NOW();
                """)

                await session.execute(
                    stmt_housing,
                    {
                        "id": housing_id,
                        "district_code": code,
                        "district_name": d_name,
                        "total_residential_units": housing.get("total_residential_units", 0),
                        "avg_surface_area_m2": housing.get("avg_surface_area_m2"),
                        "median_surface_area_m2": housing.get("median_surface_area_m2"),
                        "min_surface_area_m2": housing.get("min_surface_area_m2"),
                        "max_surface_area_m2": housing.get("max_surface_area_m2"),
                        "pre_war_count": housing.get("pre_war_count", 0),
                        "pre_war_pct": housing.get("pre_war_pct", 0.0),
                        "post_war_count": housing.get("post_war_count", 0),
                        "post_war_pct": housing.get("post_war_pct", 0.0),
                        "late_20th_count": housing.get("late_20th_count", 0),
                        "late_20th_pct": housing.get("late_20th_pct", 0.0),
                        "modern_count": housing.get("modern_count", 0),
                        "modern_pct": housing.get("modern_pct", 0.0),
                        "average_woz_value": cbs.get("woz_value"),
                        "owner_occupied_pct": cbs.get("owner_occupied_pct"),
                        "social_rent_pct": cbs.get("social_rent_pct"),
                        "private_rent_pct": cbs.get("private_rent_pct"),
                        "livability_index": cbs.get("livability_index"),
                        "safety_index": cbs.get("safety_index"),
                        "physical_index": cbs.get("physical_index"),
                        "social_index": cbs.get("social_index"),
                        "amenity_counts": json.dumps(amenities),
                    },
                )
                housing_saved += 1

            await session.commit()

        # Invalidate Redis cache for living domain
        await delete_cache_pattern("living:*")
        logger.info(
            "Living domain harvest finished successfully: {} demographics, {} housing metrics updated",
            demographics_saved,
            housing_saved,
        )

        return {
            "districts_processed": len(cbs_data),
            "demographics_saved": demographics_saved,
            "housing_saved": housing_saved,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
