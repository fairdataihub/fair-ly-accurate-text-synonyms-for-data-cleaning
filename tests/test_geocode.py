"""verify_place: a geocoder's best guess is used only when it names the text's place."""
from collections import Counter

from fairly.authorities.geocode import geocode_synonyms, is_virtual, named_countries, verify_place


def _raw(name, cls="boundary", addresstype="city", cc="it", country="Italy", **names):
    return {"name": name, "class": cls, "addresstype": addresstype,
            "address": {"country": country, "country_code": cc},
            "namedetails": dict({"name": name}, **{k.replace("_", ":"): v for k, v in names.items()})}


MILAN = _raw("Milano", name_en="Milan", name_de="Mailand")
VIENNA = _raw("Wien", cc="at", country="Austria", name_en="Vienna")


def test_translations_verify_to_the_english_name():
    assert verify_place("Milano, Italy", MILAN)["canonical"] == "Milan, Italy"
    assert verify_place("Milan", MILAN)["canonical"] == "Milan, Italy"
    assert verify_place("Wien, Österreich", VIENNA)["canonical"] == "Vienna, Austria"


def test_wrong_guesses_are_rejected():
    # a venue or a street that carries the name is not a place
    assert verify_place("Conference Location", _raw("Conference Location", cls="amenity",
                                                    addresstype="amenity", cc="ru", country="Russia")) is None
    assert verify_place("Ithaca, NY, U.S.A.", _raw("Ithaca Road", cls="highway", addresstype="road",
                                                   cc="au", country="Australia")) is None
    # the place must be named in the text
    assert verify_place("CERN", _raw("Чернь", addresstype="town", cc="ru", country="Russia", name_en="Chern",
                                     name_it="Čern'")) is None          # a foreign name folding to the text
    assert verify_place("University of Southampton",
                        _raw("Iskandar Puteri", cc="my", country="Malaysia")) is None
    # a named country or US state must agree
    assert verify_place("Venice (Italy)", _raw("Venice", cc="at", country="Austria")) is None
    assert verify_place("Paris, Texas", _raw("Paris", cc="fr", country="France")) is None
    assert verify_place("Ithaca, NY", _raw("Ithaca", cc="gr", country="Greece")) is None


def test_a_containing_region_is_not_the_city():
    pisa = _raw("Pisa", addresstype="county", official_name="Provincia di Pisa")
    assert verify_place("Pisa, Italy", pisa)["canonical"] == "Pisa, Italy"
    tuscany = _raw("Toscana", addresstype="state", name_en="Tuscany")
    assert verify_place("Pisa, Italy", tuscany) is None              # Tuscany is not named
    nc = _raw("North Carolina", addresstype="state", cc="us", country="United States")
    assert verify_place("Research Triangle Park, NC", nc) is None


def test_us_states_and_countries():
    atlanta = _raw("Atlanta", cc="us", country="United States")
    assert verify_place("Atlanta, Georgia", atlanta)["canonical"] == "Atlanta, United States"
    abq = _raw("Albuquerque", cc="us", country="United States")
    assert verify_place("Albuquerque, New Mexico", abq) is not None    # not Mexico
    assert named_countries("Ithaca, NY, U.S.A.") == [frozenset({"us"}), frozenset({"us"})]
    assert named_countries("Belfast, Northern Ireland") == [frozenset({"gb"})]
    assert verify_place("Italy", _raw("Italia", addresstype="country", name_en="Italy"))["canonical"] == "Italy"


def test_virtual_locations_are_never_geocoded():
    for t in ["Online", "virtual conference", "Zoom", "virtually", "On-line event"]:
        assert is_virtual(t), t
        assert verify_place(t, _raw(t, addresstype="city")) is None
    assert not is_virtual("Berlin / online")


def test_geocode_synonyms_uses_verified_places_only():
    raws = {"Milano, Italy": MILAN, "Milan": MILAN, "CERN": _raw("Chern", cc="ru", country="Russia"),
            "Online": _raw("Online", addresstype="city")}

    def resolve(t):
        v = verify_place(t, raws.get(t))
        return {"country": v["country"], "cc": v["cc"], "city": v["name"], "canonical": v["canonical"]} if v else None

    smap = geocode_synonyms(Counter({"Milano, Italy": 3, "Milan": 1, "CERN": 4, "Online": 2}), resolve)
    assert smap.apply("Milano, Italy") == "Milan, Italy" and smap.apply("Milan") == "Milan, Italy"
    assert smap.apply("CERN") == "CERN" and smap.apply("Online") == "Online"


def test_name_variants_area_names_and_small_places():
    gott = _raw("Göttingen", cc="de", country="Germany")
    assert verify_place("Goettingen, Germany", gott)["canonical"] == "Göttingen, Germany"
    roch = _raw("City of Rochester", cc="us", country="United States")
    assert verify_place("Rochester, NY", roch)["canonical"] == "Rochester, United States"
    arl = _raw("Arlington County", addresstype="county", cc="us", country="United States")
    assert verify_place("Arlington, VA", arl)["canonical"] == "Arlington, United States"
    padova = _raw("Padova", addresstype="county", name_en="Province of Padua")
    assert verify_place("Padova", padova)["canonical"] == "Padova, Italy"
    mars = _raw("Mars", addresstype="village", cc="fr", country="France")
    assert verify_place("Mars", mars) is None                         # a bare word, a tiny place
    oleron = _raw("Saint-Pierre-d'Oléron", addresstype="village", cc="fr", country="France")
    assert verify_place("Saint-Pierre-d'Oléron, France", oleron)["canonical"] == "Saint-Pierre-d'Oléron, France"


def test_foreign_names_count_only_with_a_named_country():
    vienna = _raw("Wien", cc="at", country="Austria", name_en="Vienna", name_fr="Vienne")
    assert verify_place("Wien", vienna)["canonical"] == "Vienna, Austria"          # its own name
    assert verify_place("Vienne", vienna) is None                                 # French name, no country
    assert verify_place("Vienne, Autriche", vienna) is None                       # "Autriche" is not in our list
    assert verify_place("Vienne, Austria", vienna)["canonical"] == "Vienna, Austria"


def test_country_names_without_their_article():
    assert named_countries("The Hague, Netherlands") == [frozenset({"nl"})]
    assert named_countries("Banjul, Gambia") == [frozenset({"gm"})]
    assert named_countries("Kinshasa, Democratic Republic of the Congo") == [frozenset({"cd"})]


def test_a_bare_name_shared_by_two_countries_is_ambiguous():
    uk = dict(_raw("Cambridge", cc="gb", country="United Kingdom"), importance=0.74)
    us = dict(_raw("Cambridge", cc="us", country="United States"), importance=0.68)
    assert verify_place("Cambridge", uk, [us]) is None
    assert verify_place("Cambridge, UK", uk, [us])["canonical"] == "Cambridge, United Kingdom"
    berlin = dict(_raw("Berlin", cc="de", country="Germany"), importance=0.85)
    berlin_nh = dict(_raw("Berlin", cc="us", country="United States"), importance=0.40)
    assert verify_place("Berlin", berlin, [berlin_nh])["canonical"] == "Berlin, Germany"
    portland_me = dict(_raw("Portland", cc="us", country="United States"), importance=0.63)
    portland_or = dict(_raw("Portland", cc="us", country="United States"), importance=0.74)
    assert verify_place("Portland", portland_or, [portland_me])["canonical"] == "Portland, United States"
