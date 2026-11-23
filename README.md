# EnergyGuard – Backend (FastAPI) v2

Recebe as leituras do ESP32, guarda no MySQL e marca anomalias com Isolation Forest.
O dashboard Streamlit consulta esta mesma API.

## 1. Instalar

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # Windows: copy .env.example .env
```

## 2. Banco de dados

MySQL: rode `schema.sql` (cria banco e usuário) e confira o `DATABASE_URL` no `.env`.
Para testar sem MySQL, use a linha do SQLite no `.env`.
As migrações do Alembic são aplicadas na inicialização e criam as tabelas quando o banco está vazio.

## 3. Rodar

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Documentação interativa: http://localhost:8000/docs
No ESP32, use o IP do computador na rede (ex.: `http://192.168.0.10:8000/api/readings`)
e libere a porta 8000 no firewall.

## 4. Testar sem hardware

Abra `/docs`, selecione `POST /api/readings` e envie o payload de exemplo abaixo.
Preencha o header `X-API-Key` com a `API_KEY` configurada.

Para rodar os testes de regressão em SQLite:

```bash
pip install pytest httpx
python -m pytest -q
```

## Endpoints (todos em `/api`, header `X-API-Key` se `API_KEY` estiver definida)

| Método | Rota | Para quê |
|---|---|---|
| POST | `/readings` | Envia uma leitura (retorna `is_anomaly`, `anomaly_score` e `reasons`) |
| POST | `/readings/batch` | Envia até 100 leituras de uma vez (`{"readings":[...]}`); é o que o firmware v2 usa, inclusive para reenviar o que ficou na fila |
| GET | `/readings?device_id=&limit=&since=` | Últimas leituras (ordem cronológica, até 20 000) |
| GET | `/readings/latest?device_id=` | Leitura mais recente |
| PUT | `/readings/{id}/feedback` | Rotula: `{"label":"real"}`, `"false"` ou `null` |
| GET | `/anomalies?device_id=&limit=` | Leituras marcadas como anomalia |
| GET | `/devices` | Dispositivos, última vez visto, Wi-Fi (RSSI), uptime e falhas de envio |
| GET | `/summary?device_id=&hours=24` | Médias, picos, energia e nº de anomalias |
| GET | `/consumption/hourly?device_id=&hours=168` | kWh por hora (UTC) |
| GET | `/quality?device_id=&hours=24&vmin=&vmax=` | % de amostras válidas com tensão/frequência fora da faixa |
| GET/POST/PUT/DELETE | `/alerts/rules` | Regras de alerta por limite |
| GET | `/alerts/events` | Histórico de alertas |
| GET / POST | `/alerts/channels`, `/alerts/test` | Canais configurados / mensagem de teste |
| GET / PUT | `/settings` | Tarifa, tensão nominal, meta mensal (kWh), intervalo de envio |
| GET / POST / DELETE | `/validations` | Comparação com multímetro/alicate |
| GET | `/model/status` · `/model/evaluation` | Estado do modelo · precisão/recall pelos seus rótulos |
| GET | `/model/evaluation/devices` | Matriz de confusão, precisão, recall, F1 e quantidade de previsões rotuladas por medidor |
| POST | `/model/train` | Treina/retreina agora |
| GET | `/health` (sem `/api`) | Checagem rápida |
| GET | `/ready` (sem `/api`) | Checagem de conexão com o banco usada pelo Blueprint do Render (503 se indisponível) |

Payload do `POST /api/readings` (os 4 últimos campos são opcionais):

```json
{"device_id":"esp32-01","voltage":127.1,"current":3.2,"power":390.5,
 "energy":1.2345,"frequency":60.0,"power_factor":0.96,
 "rssi":-61,"uptime_s":3600,"send_failures":0,"measured_ts":1761660000}
```

`measured_ts` (opcional) é o horário da medição em segundos desde 1970 (UTC). Com ele, leituras que ficaram na fila
do ESP32 entram com a hora certa. Horários inválidos (no futuro ou com mais de 7 dias) são ignorados e vale a hora
de chegada. Reenvios com horário válido e igual para o mesmo dispositivo são descartados.

As consultas cronológicas usam o horário de medição. O status online usa o horário de recebimento.
No consumo, a primeira amostra de cada medidor na janela é a referência. As diferenças seguintes
contam na hora da medição mais recente. Uma queda do contador indica reset para zero, e o cálculo
conta o valor acumulado desde o reset.

## Alertas

- **Regras por limite** (ex.: tensão < 117 V): crie pelo dashboard (aba Alertas) ou por `/alerts/rules`.
  Cada regra tem um intervalo mínimo entre avisos (`cooldown_s`) para não repetir sem parar.
- **Anomalia do Isolation Forest** também gera aviso (`NOTIFY_ON_ANOMALY`).
- **ESP32 offline** (sem dados por `OFFLINE_AFTER_S`) gera aviso, uma vez por queda.
- Os avisos ficam salvos no banco e, se configurado no `.env`, vão por **Telegram** e/ou **e-mail**.
- A API registra cada entrega por canal em `GET /api/alerts/events` (`deliveries`). Em caso de falha,
  tenta de novo após 1 minuto e aumenta o intervalo até 1 hora. A fila continua disponível após
  reiniciar a API se o banco for persistente. O campo `notified` indica que ao menos um canal confirmou o envio.

## Migrações do banco

A revisão inicial reconhece bancos das versões anteriores e adiciona as tabelas, colunas e índices ausentes.
Para aplicar as revisões antes de iniciar a API, execute na raiz do projeto, com `DATABASE_URL` configurada:

```bash
python -m alembic upgrade head
python -m alembic current
```

Faça backup antes de atualizar um banco com histórico. A revisão inicial incorpora tabelas existentes,
por isso a reversão dessa revisão é feita restaurando o backup.

## Isolation Forest

- Treina sozinho quando houver `MIN_TRAIN_SAMPLES` leituras e retreina a cada `RETRAIN_EVERY`.
- Usa tensão, corrente, potência, fator de potência e frequência.
- `anomaly_score` negativo = mais anômalo. `CONTAMINATION` define a fração esperada de anomalias.
- Treine com dados de funcionamento **normal**; anomalias entram depois.
- Leituras que você rotular como anomalia **real** saem do treino seguinte.
- A avaliação usa apenas leituras com previsão registrada e rótulo. Para medir anomalias perdidas,
  rotule também amostras que o modelo classificou como normais. Compare os medidores considerando a
  quantidade de previsões rotuladas de cada um.
- `reasons` mostra as 3 variáveis que mais se afastaram da média do treino (em desvios-padrão). É uma explicação aproximada, não a lógica interna do modelo.
- `created_at` é salvo em UTC (termina com `Z`); converta para o horário de Brasília no dashboard.

## Tipos de anomalia

O Isolation Forest diz que a leitura é estranha; regras físicas dizem o que parece estar errado
(`anomaly_types` na leitura, o primeiro item é o tipo principal; lista completa em `GET /api/anomaly-types`).

| Tipo | Como é identificado |
|---|---|
| Queda de energia | Tensão < 20 V depois de uma leitura normal e a corrente também sumiu |
| Falha de sensor | Tensão < 20 V com corrente presente (ZMPT sem rede) ou potência maior que a aparente |
| Subtensão / Sobretensão | Tensão fora da faixa da tensão nominal (127 V: 117–133 V; 220 V: 202–231 V) |
| Variação de frequência | Frequência fora de 59,5–60,5 Hz |
| Pico de corrente | Corrente > média + 6σ do treino e subindo de repente em relação à leitura anterior |
| Consumo elevado / abaixo do normal | Potência > média + 6σ (sem pico súbito) ou muito abaixo do normal |
| Fator de potência baixo | FP < 0,7 com potência acima de 20 W |
| Comportamento incomum | Nenhuma regra acima, mas o modelo estranhou a combinação |

A tensão nominal vem de Configurações do dashboard. Uma anomalia pode ter mais de um tipo.
Leituras antigas, de antes desta versão, aparecem como "Sem classificação".
