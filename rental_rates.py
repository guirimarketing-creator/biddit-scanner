# Estimated average monthly rent per m² by city (€/m²/month).
# Based on CIB Huurbarometer & Statbel data (2023-2024 figures).
# Edit these values to keep them up to date.

CITY_RATES: dict[str, float] = {
    # Antwerpen province
    "antwerpen": 14.0,
    "mechelen": 12.5,
    "turnhout": 10.5,
    "lier": 11.0,
    "herentals": 10.5,
    "mol": 9.5,
    "geel": 9.5,
    "mortsel": 12.0,
    "wilrijk": 12.5,
    "boom": 10.0,
    "beerse": 9.5,
    "olen": 9.0,
    "westerlo": 9.0,
    "hoogstraten": 9.5,
    "arendonk": 9.0,
    "balen": 9.0,

    # Oost-Vlaanderen
    "gent": 14.5,
    "aalst": 11.0,
    "sint-niklaas": 11.0,
    "dendermonde": 10.5,
    "ronse": 9.5,
    "lokeren": 10.5,
    "zottegem": 10.0,
    "ninove": 10.0,
    "oudenaarde": 10.5,
    "geraardsbergen": 9.5,
    "eeklo": 10.0,
    "wetteren": 10.5,
    "maldegem": 10.0,
    "temse": 10.5,
    "beveren": 10.5,

    # Vlaams-Brabant
    "leuven": 15.0,
    "vilvoorde": 12.0,
    "halle": 12.0,
    "tienen": 11.0,
    "diest": 11.0,
    "aarschot": 10.5,
    "haacht": 10.5,
    "overijse": 13.0,
    "tervuren": 13.5,
    "zaventem": 13.0,
    "machelen": 12.0,
    "grimbergen": 12.5,

    # Limburg
    "hasselt": 11.0,
    "genk": 10.5,
    "tongeren": 10.0,
    "maaseik": 9.5,
    "lommel": 9.5,
    "beringen": 9.5,
    "heusden-zolder": 10.0,
    "leopoldsburg": 9.5,
    "sint-truiden": 10.0,
    "bilzen": 10.0,
    "peer": 9.0,
    "herk-de-stad": 9.5,
    "bree": 9.0,
    "dilsen-stokkem": 9.0,
    "maasmechelen": 10.0,
    "lanaken": 10.5,
}

# Province-level fallback rates (€/m²/month)
PROVINCE_RATES: dict[str, float] = {
    "Antwerpen": 11.0,
    "Oost-Vlaanderen": 11.0,
    "Vlaams-Brabant": 12.0,
    "Limburg": 10.0,
}

DEFAULT_RATE = 10.0  # Absolute fallback


def get_rent_rate(city: str, province: str) -> float:
    if city:
        rate = CITY_RATES.get(city.lower().strip())
        if rate:
            return rate
    rate = PROVINCE_RATES.get(province)
    if rate:
        return rate
    return DEFAULT_RATE
