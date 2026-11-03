TYPES = {
    "queda": ("Queda de energia", "Tensão e corrente sumiram de repente."),
    "sensor": ("Falha de sensor", "Valores incoerentes, como corrente sem tensão ou potência maior que a aparente."),
    "sobretensao": ("Sobretensão", "Tensão acima da faixa adequada."),
    "subtensao": ("Subtensão", "Tensão abaixo da faixa adequada."),
    "frequencia": ("Variação de frequência", "Frequência fora de 59,5 a 60,5 Hz."),
    "sobrecorrente": ("Pico de corrente", "Corrente muito acima do normal e crescendo de repente."),
    "consumo_elevado": ("Consumo elevado", "Potência muito acima do comportamento normal, sem ser um pico súbito."),
    "consumo_baixo": ("Consumo abaixo do normal", "Potência muito abaixo do normal para essa carga."),
    "fp_baixo": ("Fator de potência baixo", "FP abaixo de 0,7 com carga relevante (carga indutiva)."),
    "incomum": ("Comportamento incomum", "O modelo estranhou a combinação das variáveis, sem uma causa específica."),
}
ORDER = list(TYPES)

MIN_MAINS_V = 20.0
MIN_CURRENT_A = 0.15
SIGMA = 6.0
FREQ_MIN = 59.5
FREQ_MAX = 60.5
MIN_PF = 0.7
MIN_PF_POWER_W = 20.0


def voltage_range(nominal: float) -> tuple[float, float]:
    fixed = {127: (117.0, 133.0), 220: (202.0, 231.0)}
    return fixed.get(round(nominal), (nominal * 0.92, nominal * 1.05))


def classify(reading, prev, stats: dict | None, nominal: float) -> list[str]:
    v, i, p = reading.voltage, reading.current, reading.power
    pf, f = reading.power_factor, reading.frequency
    vmin, vmax = voltage_range(nominal)
    found: set[str] = set()

    if v < MIN_MAINS_V:
        lost_power = prev is not None and prev.voltage >= vmin and i <= MIN_CURRENT_A
        found.add("queda" if lost_power else "sensor")
    else:
        if v < vmin:
            found.add("subtensao")
        elif v > vmax:
            found.add("sobretensao")
        if f > 0 and not (FREQ_MIN <= f <= FREQ_MAX):
            found.add("frequencia")
        if p > v * i * 1.1 + 5:
            found.add("sensor")
        if stats:
            mean_i, std_i = stats["current"]
            mean_p, std_p = stats["power"]
            spike = i > mean_i + SIGMA * std_i and i > mean_i * 1.5 + 0.5
            sudden = prev is None or i > prev.current * 1.5 + 0.3
            if spike and sudden:
                found.add("sobrecorrente")
            elif p > mean_p + SIGMA * std_p and p > mean_p * 1.5 + 20:
                found.add("consumo_elevado")
            elif mean_p > 50 and p < mean_p - SIGMA * std_p and p < mean_p * 0.5:
                found.add("consumo_baixo")
        if pf < MIN_PF and p > MIN_PF_POWER_W and i > MIN_CURRENT_A:
            found.add("fp_baixo")

    if not found:
        found.add("incomum")
    return [code for code in ORDER if code in found]
