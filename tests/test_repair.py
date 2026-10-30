"""fairly.repair: text a PDF extraction damaged, repaired from a reference or a vocabulary."""
from fairly.repair import has_word, repair_from_reference, repair_ligatures, undouble, word_counts

F = "\ufffd"


def test_has_word_in_any_script():
    for name in ("李, 杰", "Попова", "Ng, Li",
                 "सुश्री प्रीति"):
        assert has_word(name)
    for name in ("M., A", "D", "", None, "123"):
        assert not has_word(name)


def test_word_counts_case_folded_without_markup():
    assert word_counts(["<b>Federation</b> University", "federation", 3]) == {"federation": 2, "university": 1}


def test_repair_ligatures_fills_known_words_in_their_case():
    vocab = {"federation": 5, "meeting": 9, "cognitive": 4, "forschungsgemeinschaft": 7, "th": 99, "insti": 5}
    assert repair_ligatures(f"Federa{F}on University", vocab) == "Federation University"
    assert repair_ligatures(f"Annual Mee{F}ng of the Cogni{F}ve Society", vocab) == "Annual Meeting of the Cognitive Society"
    assert repair_ligatures(f"ANNUAL MEE{F}NG", vocab) == "ANNUAL MEETING"
    assert repair_ligatures(f"Deutsche Forschungsgemeinscha{F} (DFG)", vocab) == "Deutsche Forschungsgemeinschaft (DFG)"
    # unknown words, a glyph in a formula, a word split across a line: unchanged
    assert repair_ligatures(f"UMR Gene{F}", vocab) == f"UMR Gene{F}"
    assert repair_ligatures(f"xx {F} mm ll {F}", vocab) == f"xx {F} mm ll {F}"
    assert repair_ligatures(f"Die Ins{F} tu{F} on", vocab) == f"Die Ins{F} tu{F} on"
    # a very common word completes at a word end too
    assert repair_ligatures(f"mul{F}-band and so{F} matter", {"multi": 400, "soft": 90}) == "multi-band and soft matter"
    assert repair_ligatures("no damage", vocab) == "no damage"


def test_undouble():
    assert undouble("VIAS VIAS AEREAS AEREAS POR POR CORPO CORPO (OVACE)") == "VIAS AEREAS POR CORPO (OVACE)"
    assert undouble("New New York city of of the") == "New New York city of of the"


def test_repair_from_reference_fixes_damaged_words_only():
    assert repair_from_reference(f"Non-alcoholic fa{F}y liver disease from an omics approach",
                                 ["Non-alcoholic fatty liver disease from an omics approach"]) == \
        "Non-alcoholic fatty liver disease from an omics approach"
    assert repair_from_reference("Analise odontologica, em especial 'flor de lis', para identificacao forense",
                                 ['Análise Odontológica, em Especial "Flor de Lis", para '
                                  'Identificação Forense: Relato']) == \
        "Análise odontológica, em especial 'flor de lis', para identificação forense"
    assert repair_from_reference("AnalisE EpidemiolÓgica Das Fraturas Na Grande SÃo Paulo",
                                 ["Análise epidemiológica das fraturas na Grande São Paulo"]) == \
        "Análise epidemiológica das fraturas na Grande São Paulo"
    assert repair_from_reference(f"Life-cycles synchronisa{F}on ma{F}ers in maize",
                                 ["Maize resistance: life-cycles synchronisation matters in maize.pdf"]) == \
        "Life-cycles synchronisation matters in maize"
    assert repair_from_reference("VIAS VIAS AEREAS AEREAS POR POR CORPO CORPO (OVACE)",
                                 ["VIAS AÉREAS POR CORPO (OVACE)"]) == "VIAS AÉREAS POR CORPO (OVACE)"


def test_clean_text_is_never_restyled():
    for text, ref in (("SCHOLARLY PUBLISHING IN THE EUROPEAN RESEARCH AREA (ERA)",
                       "Scholarly Publishing in the European Research Area (ERA)"),
                      ("King's College London", "King’s College London"),
                      ("healthcare workers", "health care workers"),
                      ("Hamburg, Germany", "held in Hamburg (Germany) 2023"),
                      ("Magellanic Clouds", "the Magellanic Cloud's stars"),
                      ("DiVaM 2018 Patrimonio que futuro?", "Do Saber ao Criar: Villa de Milreu")):
        assert repair_from_reference(text, [ref]) is None
    # ambiguous: the words occur twice in the reference
    assert repair_from_reference("Analise de dados abertos", ["Análise de dados abertos. Análise de dados abertos"]) is None
