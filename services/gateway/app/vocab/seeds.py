"""Static vocabulary seeds — ~30 en→ko terms per domain.

UUIDs are deterministic via uuid5 so re-seeding is idempotent.
Each entry seeds the en→ko direction; the seeder can be extended to ko→en
by swapping source_lang/target_lang.
"""

from __future__ import annotations

from uuid import NAMESPACE_URL, UUID, uuid5

TOPIC_SEEDS: dict[str, list[dict]] = {
    "logistics": [
        {"term": "supply chain", "definition": "공급망", "register": "formal-military"},
        {"term": "requisition", "definition": "청구", "register": "formal-military"},
        {"term": "procurement", "definition": "조달", "register": "formal-military"},
        {"term": "inventory", "definition": "재고", "register": "formal-military"},
        {"term": "manifest", "definition": "화물 목록", "register": "formal-military"},
        {"term": "sortie", "definition": "출격", "register": "formal-military"},
        {"term": "airlift", "definition": "공수", "register": "formal-military"},
        {"term": "sealift", "definition": "해상 수송", "register": "formal-military"},
        {"term": "convoy", "definition": "호송대", "register": "formal-military"},
        {"term": "depot", "definition": "보급 창고", "register": "formal-military"},
        {"term": "throughput", "definition": "처리량", "register": "formal-military"},
        {"term": "forward operating base", "definition": "전진 작전 기지", "register": "formal-military"},
        {"term": "distribution hub", "definition": "물류 거점", "register": "formal-military"},
        {"term": "stockpile", "definition": "비축물", "register": "formal-military"},
        {"term": "echelon", "definition": "제대", "register": "formal-military"},
        {"term": "attrition rate", "definition": "소모율", "register": "formal-military"},
        {"term": "lead time", "definition": "조달 소요 시간", "register": "formal-military"},
        {"term": "containerized cargo", "definition": "컨테이너 화물", "register": "formal-military"},
        {"term": "hazardous material", "definition": "위험물", "register": "formal-military"},
        {"term": "load plan", "definition": "적재 계획", "register": "formal-military"},
        {"term": "palletize", "definition": "팔레트에 적재하다", "register": "formal-military"},
        {"term": "retrograde", "definition": "후방 이송", "register": "formal-military"},
        {"term": "sustainment", "definition": "전투 지속 지원", "register": "formal-military"},
        {"term": "cross-leveling", "definition": "횡적 균형 배분", "register": "formal-military"},
        {"term": "pre-positioning", "definition": "사전 배치", "register": "formal-military"},
        {"term": "ammunition", "definition": "탄약", "register": "formal-military"},
        {"term": "fuel resupply", "definition": "연료 재보급", "register": "formal-military"},
        {"term": "medical supplies", "definition": "의료 물자", "register": "formal-military"},
        {"term": "maintenance cycle", "definition": "정비 주기", "register": "formal-military"},
        {"term": "bottleneck", "definition": "병목 현상", "register": "formal-military"},
    ],
    "diplomacy": [
        {"term": "communiqué", "definition": "공동 성명", "register": "formal-diplomatic"},
        {"term": "bilateral", "definition": "양자 간", "register": "formal-diplomatic"},
        {"term": "multilateral", "definition": "다자 간", "register": "formal-diplomatic"},
        {"term": "ratify", "definition": "비준하다", "register": "formal-diplomatic"},
        {"term": "normalization", "definition": "정상화", "register": "formal-diplomatic"},
        {"term": "sanction", "definition": "제재", "register": "formal-diplomatic"},
        {"term": "envoy", "definition": "특사", "register": "formal-diplomatic"},
        {"term": "memorandum of understanding", "definition": "양해각서", "register": "formal-diplomatic"},
        {"term": "sovereignty", "definition": "주권", "register": "formal-diplomatic"},
        {"term": "diplomatic immunity", "definition": "외교적 면책특권", "register": "formal-diplomatic"},
        {"term": "persona non grata", "definition": "기피 인물", "register": "formal-diplomatic"},
        {"term": "treaty", "definition": "조약", "register": "formal-diplomatic"},
        {"term": "ceasefire", "definition": "휴전", "register": "formal-diplomatic"},
        {"term": "armistice", "definition": "정전 협정", "register": "formal-diplomatic"},
        {"term": "demilitarized zone", "definition": "비무장지대", "register": "formal-diplomatic"},
        {"term": "good offices", "definition": "주선", "register": "formal-diplomatic"},
        {"term": "summit", "definition": "정상회담", "register": "formal-diplomatic"},
        {"term": "communiqué draft", "definition": "공동 성명 초안", "register": "formal-diplomatic"},
        {"term": "protocol", "definition": "의정서", "register": "formal-diplomatic"},
        {"term": "annexure", "definition": "부속서", "register": "formal-diplomatic"},
        {"term": "interlocutor", "definition": "대화 상대방", "register": "formal-diplomatic"},
        {"term": "back-channel", "definition": "비공식 채널", "register": "formal-diplomatic"},
        {"term": "détente", "definition": "긴장 완화", "register": "formal-diplomatic"},
        {"term": "rapprochement", "definition": "관계 개선", "register": "formal-diplomatic"},
        {"term": "demarche", "definition": "외교적 항의", "register": "formal-diplomatic"},
        {"term": "consular", "definition": "영사의", "register": "formal-diplomatic"},
        {"term": "ultimatum", "definition": "최후 통첩", "register": "formal-diplomatic"},
        {"term": "provisional agreement", "definition": "잠정 합의", "register": "formal-diplomatic"},
        {"term": "joint declaration", "definition": "공동 선언", "register": "formal-diplomatic"},
        {"term": "observer status", "definition": "참관국 지위", "register": "formal-diplomatic"},
    ],
    "intelligence": [
        {"term": "reconnaissance", "definition": "정찰", "register": "formal-military"},
        {"term": "surveillance", "definition": "감시", "register": "formal-military"},
        {"term": "signals intelligence", "definition": "신호 정보", "register": "formal-military"},
        {"term": "human intelligence", "definition": "인간 정보", "register": "formal-military"},
        {"term": "imagery intelligence", "definition": "영상 정보", "register": "formal-military"},
        {"term": "open-source intelligence", "definition": "공개 출처 정보", "register": "formal-military"},
        {"term": "counterintelligence", "definition": "방첩", "register": "formal-military"},
        {"term": "covert operation", "definition": "비밀 작전", "register": "formal-military"},
        {"term": "asset", "definition": "정보 자산", "register": "formal-military"},
        {"term": "handler", "definition": "담당 공작원", "register": "formal-military"},
        {"term": "cover story", "definition": "위장 신분", "register": "formal-military"},
        {"term": "dead drop", "definition": "비밀 정보 전달 장소", "register": "formal-military"},
        {"term": "tradecraft", "definition": "공작 기술", "register": "formal-military"},
        {"term": "exploitation", "definition": "정보 활용", "register": "formal-military"},
        {"term": "fusion center", "definition": "정보 통합 센터", "register": "formal-military"},
        {"term": "order of battle", "definition": "전투 서열", "register": "formal-military"},
        {"term": "threat assessment", "definition": "위협 평가", "register": "formal-military"},
        {"term": "indicators and warnings", "definition": "징후 및 경보", "register": "formal-military"},
        {"term": "collection plan", "definition": "수집 계획", "register": "formal-military"},
        {"term": "dissemination", "definition": "배포", "register": "formal-military"},
        {"term": "compartmentalization", "definition": "정보 구획화", "register": "formal-military"},
        {"term": "need-to-know", "definition": "지득 필요성", "register": "formal-military"},
        {"term": "classification level", "definition": "비밀 등급", "register": "formal-military"},
        {"term": "red team", "definition": "레드팀", "register": "formal-military"},
        {"term": "deception operation", "definition": "기만 작전", "register": "formal-military"},
        {"term": "exfiltrate", "definition": "비밀 탈출시키다", "register": "formal-military"},
        {"term": "intercept", "definition": "감청", "register": "formal-military"},
        {"term": "electronic warfare", "definition": "전자전", "register": "formal-military"},
        {"term": "targeting cycle", "definition": "표적 선정 주기", "register": "formal-military"},
        {"term": "ground truth", "definition": "실제 상황", "register": "formal-military"},
    ],
    "operations": [
        {"term": "rules of engagement", "definition": "교전 규칙", "register": "formal-military"},
        {"term": "command and control", "definition": "지휘 통제", "register": "formal-military"},
        {"term": "fire support", "definition": "화력 지원", "register": "formal-military"},
        {"term": "close air support", "definition": "근접 항공 지원", "register": "formal-military"},
        {"term": "maneuver", "definition": "기동", "register": "formal-military"},
        {"term": "flank", "definition": "측면", "register": "formal-military"},
        {"term": "envelopment", "definition": "포위 기동", "register": "formal-military"},
        {"term": "perimeter defense", "definition": "주변 방어", "register": "formal-military"},
        {"term": "blocking position", "definition": "차단 진지", "register": "formal-military"},
        {"term": "breach", "definition": "돌파구 개설", "register": "formal-military"},
        {"term": "exploitation phase", "definition": "전과 확대 단계", "register": "formal-military"},
        {"term": "consolidation", "definition": "진지 강화", "register": "formal-military"},
        {"term": "combat power", "definition": "전투력", "register": "formal-military"},
        {"term": "operational tempo", "definition": "작전 속도", "register": "formal-military"},
        {"term": "deconfliction", "definition": "임무 충돌 방지", "register": "formal-military"},
        {"term": "fratricide", "definition": "아군 오사", "register": "formal-military"},
        {"term": "battle rhythm", "definition": "전투 리듬", "register": "formal-military"},
        {"term": "scheme of maneuver", "definition": "기동 구상", "register": "formal-military"},
        {"term": "axis of advance", "definition": "진격 축선", "register": "formal-military"},
        {"term": "phase line", "definition": "단계 통제선", "register": "formal-military"},
        {"term": "checkpoints", "definition": "검문소", "register": "formal-military"},
        {"term": "cordon and search", "definition": "포위 수색", "register": "formal-military"},
        {"term": "direct action", "definition": "직접 행동 임무", "register": "formal-military"},
        {"term": "air assault", "definition": "공중 강습", "register": "formal-military"},
        {"term": "amphibious operation", "definition": "상륙 작전", "register": "formal-military"},
        {"term": "suppression", "definition": "제압", "register": "formal-military"},
        {"term": "objective rally point", "definition": "목표 집결 지점", "register": "formal-military"},
        {"term": "battle handover", "definition": "전투 인계", "register": "formal-military"},
        {"term": "relief in place", "definition": "진지 교대", "register": "formal-military"},
        {"term": "passage of lines", "definition": "부대 통과", "register": "formal-military"},
    ],
    "medical": [
        {"term": "triage", "definition": "부상자 분류", "register": "formal-military"},
        {"term": "medevac", "definition": "의무 후송", "register": "formal-military"},
        {"term": "tourniquet", "definition": "지혈대", "register": "formal-military"},
        {"term": "hemorrhage", "definition": "출혈", "register": "formal-military"},
        {"term": "trauma", "definition": "외상", "register": "formal-military"},
        {"term": "casualty", "definition": "사상자", "register": "formal-military"},
        {"term": "vital signs", "definition": "활력 징후", "register": "formal-military"},
        {"term": "airway management", "definition": "기도 관리", "register": "formal-military"},
        {"term": "field dressing", "definition": "야전 처치", "register": "formal-military"},
        {"term": "burn victim", "definition": "화상 환자", "register": "formal-military"},
        {"term": "blast injury", "definition": "폭발 부상", "register": "formal-military"},
        {"term": "hypothermia", "definition": "저체온증", "register": "formal-military"},
        {"term": "dehydration", "definition": "탈수", "register": "formal-military"},
        {"term": "point of injury", "definition": "부상 지점", "register": "formal-military"},
        {"term": "mass casualty incident", "definition": "대규모 사상자 사건", "register": "formal-military"},
        {"term": "surgical team", "definition": "수술팀", "register": "formal-military"},
        {"term": "forward surgical team", "definition": "전방 수술팀", "register": "formal-military"},
        {"term": "blood transfusion", "definition": "수혈", "register": "formal-military"},
        {"term": "intravenous fluids", "definition": "정맥 수액", "register": "formal-military"},
        {"term": "analgesia", "definition": "진통제", "register": "formal-military"},
        {"term": "sedation", "definition": "진정", "register": "formal-military"},
        {"term": "contamination", "definition": "오염", "register": "formal-military"},
        {"term": "decontamination", "definition": "제독", "register": "formal-military"},
        {"term": "chemical exposure", "definition": "화학물질 노출", "register": "formal-military"},
        {"term": "quarantine", "definition": "격리", "register": "formal-military"},
        {"term": "infectious disease", "definition": "감염병", "register": "formal-military"},
        {"term": "prophylaxis", "definition": "예방 처치", "register": "formal-military"},
        {"term": "orthopaedic injury", "definition": "정형외과적 부상", "register": "formal-military"},
        {"term": "concussion", "definition": "뇌진탕", "register": "formal-military"},
        {"term": "evacuation chain", "definition": "후송 체계", "register": "formal-military"},
    ],
    "cyber": [
        {"term": "intrusion", "definition": "침입", "register": "formal-military"},
        {"term": "malware", "definition": "악성 소프트웨어", "register": "formal-military"},
        {"term": "ransomware", "definition": "랜섬웨어", "register": "formal-military"},
        {"term": "zero-day exploit", "definition": "제로데이 취약점 공격", "register": "formal-military"},
        {"term": "phishing", "definition": "피싱", "register": "formal-military"},
        {"term": "denial of service", "definition": "서비스 거부 공격", "register": "formal-military"},
        {"term": "command-and-control server", "definition": "명령 제어 서버", "register": "formal-military"},
        {"term": "lateral movement", "definition": "수평 이동", "register": "formal-military"},
        {"term": "privilege escalation", "definition": "권한 상승", "register": "formal-military"},
        {"term": "exfiltration", "definition": "데이터 유출", "register": "formal-military"},
        {"term": "patch", "definition": "보안 패치", "register": "formal-military"},
        {"term": "firewall", "definition": "방화벽", "register": "formal-military"},
        {"term": "encryption", "definition": "암호화", "register": "formal-military"},
        {"term": "decryption", "definition": "복호화", "register": "formal-military"},
        {"term": "backdoor", "definition": "백도어", "register": "formal-military"},
        {"term": "supply chain attack", "definition": "공급망 공격", "register": "formal-military"},
        {"term": "social engineering", "definition": "사회공학적 공격", "register": "formal-military"},
        {"term": "threat actor", "definition": "위협 행위자", "register": "formal-military"},
        {"term": "attribution", "definition": "공격 주체 귀속", "register": "formal-military"},
        {"term": "incident response", "definition": "침해 대응", "register": "formal-military"},
        {"term": "forensics", "definition": "디지털 포렌식", "register": "formal-military"},
        {"term": "vulnerability assessment", "definition": "취약점 평가", "register": "formal-military"},
        {"term": "penetration testing", "definition": "침투 테스트", "register": "formal-military"},
        {"term": "critical infrastructure", "definition": "핵심 기반시설", "register": "formal-military"},
        {"term": "air gap", "definition": "에어 갭", "register": "formal-military"},
        {"term": "insider threat", "definition": "내부자 위협", "register": "formal-military"},
        {"term": "offensive cyber operation", "definition": "공세적 사이버 작전", "register": "formal-military"},
        {"term": "defensive cyber operation", "definition": "방어적 사이버 작전", "register": "formal-military"},
        {"term": "cyber resilience", "definition": "사이버 복원력", "register": "formal-military"},
        {"term": "nation-state actor", "definition": "국가 행위자", "register": "formal-military"},
    ],
}


# ---------------------------------------------------------------------------
# EN ↔ ES seed set
# ---------------------------------------------------------------------------
# Populated by `scripts/seed_es_vocab.py` (one-shot Claude generator).
# Until that runs and commits the data back here, EN_ES_TOPIC_SEEDS is
# empty and the seeder falls back to extraction-only for the en↔es pair.
# Shape mirrors TOPIC_SEEDS: term is the English form, definition is
# the Spanish translation, register matches the source domain.

EN_ES_TOPIC_SEEDS: dict[str, list[dict]] = {
    "logistics": [
        {"term": "supply chain", "definition": "cadena de suministro", "register": "formal-military"},
        {"term": "requisition", "definition": "requisición", "register": "formal-military"},
        {"term": "procurement", "definition": "adquisición", "register": "formal-military"},
        {"term": "inventory", "definition": "inventario", "register": "formal-military"},
        {"term": "manifest", "definition": "manifiesto de carga", "register": "formal-military"},
        {"term": "sortie", "definition": "salida", "register": "formal-military"},
        {"term": "airlift", "definition": "puente aéreo", "register": "formal-military"},
        {"term": "sealift", "definition": "transporte marítimo de carga militar", "register": "formal-military"},
        {"term": "convoy", "definition": "convoy", "register": "formal-military"},
        {"term": "depot", "definition": "depósito", "register": "formal-military"},
        {"term": "throughput", "definition": "capacidad de paso", "register": "formal-military"},
        {"term": "forward operating base", "definition": "base de operaciones avanzada", "register": "formal-military"},
        {"term": "distribution hub", "definition": "nodo de distribución", "register": "formal-military"},
        {"term": "stockpile", "definition": "reserva estratégica", "register": "formal-military"},
        {"term": "echelon", "definition": "escalón", "register": "formal-military"},
        {"term": "attrition rate", "definition": "tasa de desgaste", "register": "formal-military"},
        {"term": "lead time", "definition": "plazo de aprovisionamiento", "register": "formal-military"},
        {"term": "containerized cargo", "definition": "carga contenerizada", "register": "formal-military"},
        {"term": "hazardous material", "definition": "material peligroso", "register": "formal-military"},
        {"term": "load plan", "definition": "plan de carga", "register": "formal-military"},
        {"term": "palletize", "definition": "paletizar", "register": "formal-military"},
        {"term": "retrograde", "definition": "repliegue", "register": "formal-military"},
        {"term": "sustainment", "definition": "sostenimiento", "register": "formal-military"},
        {"term": "cross-leveling", "definition": "nivelación cruzada", "register": "formal-military"},
        {"term": "pre-positioning", "definition": "preposicionamiento", "register": "formal-military"},
        {"term": "ammunition", "definition": "munición", "register": "formal-military"},
        {"term": "fuel resupply", "definition": "reabastecimiento de combustible", "register": "formal-military"},
        {"term": "medical supplies", "definition": "material sanitario", "register": "formal-military"},
        {"term": "maintenance cycle", "definition": "ciclo de mantenimiento", "register": "formal-military"},
        {"term": "bottleneck", "definition": "cuello de botella", "register": "formal-military"},
    ],
    "diplomacy": [
        {"term": "communiqué", "definition": "comunicado", "register": "formal-diplomatic"},
        {"term": "bilateral", "definition": "bilateral", "register": "formal-diplomatic"},
        {"term": "multilateral", "definition": "multilateral", "register": "formal-diplomatic"},
        {"term": "ratify", "definition": "ratificar", "register": "formal-diplomatic"},
        {"term": "normalization", "definition": "normalización", "register": "formal-diplomatic"},
        {"term": "sanction", "definition": "sanción", "register": "formal-diplomatic"},
        {"term": "envoy", "definition": "enviado", "register": "formal-diplomatic"},
        {"term": "memorandum of understanding", "definition": "memorando de entendimiento", "register": "formal-diplomatic"},
        {"term": "sovereignty", "definition": "soberanía", "register": "formal-diplomatic"},
        {"term": "diplomatic immunity", "definition": "inmunidad diplomática", "register": "formal-diplomatic"},
        {"term": "persona non grata", "definition": "persona non grata", "register": "formal-diplomatic"},
        {"term": "treaty", "definition": "tratado", "register": "formal-diplomatic"},
        {"term": "ceasefire", "definition": "alto el fuego", "register": "formal-diplomatic"},
        {"term": "armistice", "definition": "armisticio", "register": "formal-diplomatic"},
        {"term": "demilitarized zone", "definition": "zona desmilitarizada", "register": "formal-diplomatic"},
        {"term": "good offices", "definition": "buenos oficios", "register": "formal-diplomatic"},
        {"term": "summit", "definition": "cumbre", "register": "formal-diplomatic"},
        {"term": "communiqué draft", "definition": "proyecto de comunicado", "register": "formal-diplomatic"},
        {"term": "protocol", "definition": "protocolo", "register": "formal-diplomatic"},
        {"term": "annexure", "definition": "anexo", "register": "formal-diplomatic"},
        {"term": "interlocutor", "definition": "interlocutor", "register": "formal-diplomatic"},
        {"term": "back-channel", "definition": "canal reservado", "register": "formal-diplomatic"},
        {"term": "détente", "definition": "distensión", "register": "formal-diplomatic"},
        {"term": "rapprochement", "definition": "acercamiento", "register": "formal-diplomatic"},
        {"term": "demarche", "definition": "démarche", "register": "formal-diplomatic"},
        {"term": "consular", "definition": "consular", "register": "formal-diplomatic"},
        {"term": "ultimatum", "definition": "ultimátum", "register": "formal-diplomatic"},
        {"term": "provisional agreement", "definition": "acuerdo provisional", "register": "formal-diplomatic"},
        {"term": "joint declaration", "definition": "declaración conjunta", "register": "formal-diplomatic"},
        {"term": "observer status", "definition": "condición de observador", "register": "formal-diplomatic"},
    ],
    "intelligence": [
        {"term": "reconnaissance", "definition": "reconocimiento", "register": "formal-military"},
        {"term": "surveillance", "definition": "vigilancia", "register": "formal-military"},
        {"term": "signals intelligence", "definition": "inteligencia de señales", "register": "formal-military"},
        {"term": "human intelligence", "definition": "inteligencia humana", "register": "formal-military"},
        {"term": "imagery intelligence", "definition": "inteligencia de imágenes", "register": "formal-military"},
        {"term": "open-source intelligence", "definition": "inteligencia de fuentes abiertas", "register": "formal-military"},
        {"term": "counterintelligence", "definition": "contrainteligencia", "register": "formal-military"},
        {"term": "covert operation", "definition": "operación encubierta", "register": "formal-military"},
        {"term": "asset", "definition": "activo", "register": "formal-military"},
        {"term": "handler", "definition": "oficial de caso", "register": "formal-military"},
        {"term": "cover story", "definition": "leyenda de cobertura", "register": "formal-military"},
        {"term": "dead drop", "definition": "buzón muerto", "register": "formal-military"},
        {"term": "tradecraft", "definition": "técnicas de inteligencia", "register": "formal-military"},
        {"term": "exploitation", "definition": "explotación", "register": "formal-military"},
        {"term": "fusion center", "definition": "centro de fusión", "register": "formal-military"},
        {"term": "order of battle", "definition": "orden de batalla", "register": "formal-military"},
        {"term": "threat assessment", "definition": "evaluación de amenazas", "register": "formal-military"},
        {"term": "indicators and warnings", "definition": "indicadores y avisos", "register": "formal-military"},
        {"term": "collection plan", "definition": "plan de obtención de información", "register": "formal-military"},
        {"term": "dissemination", "definition": "difusión", "register": "formal-military"},
        {"term": "compartmentalization", "definition": "compartimentación", "register": "formal-military"},
        {"term": "need-to-know", "definition": "necesidad de conocer", "register": "formal-military"},
        {"term": "classification level", "definition": "nivel de clasificación", "register": "formal-military"},
        {"term": "red team", "definition": "equipo rojo", "register": "formal-military"},
        {"term": "deception operation", "definition": "operación de engaño", "register": "formal-military"},
        {"term": "exfiltrate", "definition": "exfiltrar", "register": "formal-military"},
        {"term": "intercept", "definition": "interceptación", "register": "formal-military"},
        {"term": "electronic warfare", "definition": "guerra electrónica", "register": "formal-military"},
        {"term": "targeting cycle", "definition": "ciclo de selección de objetivos", "register": "formal-military"},
        {"term": "ground truth", "definition": "verdad sobre el terreno", "register": "formal-military"},
    ],
    "operations": [
        {"term": "rules of engagement", "definition": "reglas de enfrentamiento", "register": "formal-military"},
        {"term": "command and control", "definition": "mando y control", "register": "formal-military"},
        {"term": "fire support", "definition": "apoyo de fuegos", "register": "formal-military"},
        {"term": "close air support", "definition": "apoyo aéreo cercano", "register": "formal-military"},
        {"term": "maneuver", "definition": "maniobra", "register": "formal-military"},
        {"term": "flank", "definition": "flanco", "register": "formal-military"},
        {"term": "envelopment", "definition": "envolvimiento", "register": "formal-military"},
        {"term": "perimeter defense", "definition": "defensa perimetral", "register": "formal-military"},
        {"term": "blocking position", "definition": "posición de bloqueo", "register": "formal-military"},
        {"term": "breach", "definition": "brecha", "register": "formal-military"},
        {"term": "exploitation phase", "definition": "fase de explotación", "register": "formal-military"},
        {"term": "consolidation", "definition": "consolidación", "register": "formal-military"},
        {"term": "combat power", "definition": "poder de combate", "register": "formal-military"},
        {"term": "operational tempo", "definition": "ritmo operacional", "register": "formal-military"},
        {"term": "deconfliction", "definition": "desconflicción", "register": "formal-military"},
        {"term": "fratricide", "definition": "fratricidio", "register": "formal-military"},
        {"term": "battle rhythm", "definition": "ritmo de batalla", "register": "formal-military"},
        {"term": "scheme of maneuver", "definition": "concepto de la maniobra", "register": "formal-military"},
        {"term": "axis of advance", "definition": "eje de avance", "register": "formal-military"},
        {"term": "phase line", "definition": "línea de fase", "register": "formal-military"},
        {"term": "checkpoints", "definition": "puestos de control", "register": "formal-military"},
        {"term": "cordon and search", "definition": "cerco y registro", "register": "formal-military"},
        {"term": "direct action", "definition": "acción directa", "register": "formal-military"},
        {"term": "air assault", "definition": "asalto aéreo", "register": "formal-military"},
        {"term": "amphibious operation", "definition": "operación anfibia", "register": "formal-military"},
        {"term": "suppression", "definition": "supresión", "register": "formal-military"},
        {"term": "objective rally point", "definition": "punto de reunión del objetivo", "register": "formal-military"},
        {"term": "battle handover", "definition": "relevo en el combate", "register": "formal-military"},
        {"term": "relief in place", "definition": "relevo en posición", "register": "formal-military"},
        {"term": "passage of lines", "definition": "paso de líneas", "register": "formal-military"},
    ],
    "medical": [
        {"term": "triage", "definition": "triaje", "register": "formal-military"},
        {"term": "medevac", "definition": "evacuación médica", "register": "formal-military"},
        {"term": "tourniquet", "definition": "torniquete", "register": "formal-military"},
        {"term": "hemorrhage", "definition": "hemorragia", "register": "formal-military"},
        {"term": "trauma", "definition": "traumatismo", "register": "formal-military"},
        {"term": "casualty", "definition": "baja", "register": "formal-military"},
        {"term": "vital signs", "definition": "signos vitales", "register": "formal-military"},
        {"term": "airway management", "definition": "manejo de la vía aérea", "register": "formal-military"},
        {"term": "field dressing", "definition": "vendaje de campaña", "register": "formal-military"},
        {"term": "burn victim", "definition": "víctima de quemaduras", "register": "formal-military"},
        {"term": "blast injury", "definition": "traumatismo por explosión", "register": "formal-military"},
        {"term": "hypothermia", "definition": "hipotermia", "register": "formal-military"},
        {"term": "dehydration", "definition": "deshidratación", "register": "formal-military"},
        {"term": "point of injury", "definition": "punto de lesión", "register": "formal-military"},
        {"term": "mass casualty incident", "definition": "incidente de víctimas en masa", "register": "formal-military"},
        {"term": "surgical team", "definition": "equipo quirúrgico", "register": "formal-military"},
        {"term": "forward surgical team", "definition": "equipo quirúrgico avanzado", "register": "formal-military"},
        {"term": "blood transfusion", "definition": "transfusión de sangre", "register": "formal-military"},
        {"term": "intravenous fluids", "definition": "fluidos intravenosos", "register": "formal-military"},
        {"term": "analgesia", "definition": "analgesia", "register": "formal-military"},
        {"term": "sedation", "definition": "sedación", "register": "formal-military"},
        {"term": "contamination", "definition": "contaminación", "register": "formal-military"},
        {"term": "decontamination", "definition": "descontaminación", "register": "formal-military"},
        {"term": "chemical exposure", "definition": "exposición a agentes químicos", "register": "formal-military"},
        {"term": "quarantine", "definition": "cuarentena", "register": "formal-military"},
        {"term": "infectious disease", "definition": "enfermedad infecciosa", "register": "formal-military"},
        {"term": "prophylaxis", "definition": "profilaxis", "register": "formal-military"},
        {"term": "orthopaedic injury", "definition": "lesión ortopédica", "register": "formal-military"},
        {"term": "concussion", "definition": "conmoción cerebral", "register": "formal-military"},
        {"term": "evacuation chain", "definition": "cadena de evacuación", "register": "formal-military"},
    ],
    "cyber": [
        {"term": "intrusion", "definition": "intrusión", "register": "formal-military"},
        {"term": "malware", "definition": "programa malicioso", "register": "formal-military"},
        {"term": "ransomware", "definition": "ransomware", "register": "formal-military"},
        {"term": "zero-day exploit", "definition": "exploit de día cero", "register": "formal-military"},
        {"term": "phishing", "definition": "suplantación de identidad", "register": "formal-military"},
        {"term": "denial of service", "definition": "denegación de servicio", "register": "formal-military"},
        {"term": "command-and-control server", "definition": "servidor de mando y control", "register": "formal-military"},
        {"term": "lateral movement", "definition": "movimiento lateral", "register": "formal-military"},
        {"term": "privilege escalation", "definition": "escalada de privilegios", "register": "formal-military"},
        {"term": "exfiltration", "definition": "exfiltración", "register": "formal-military"},
        {"term": "patch", "definition": "parche", "register": "formal-military"},
        {"term": "firewall", "definition": "cortafuegos", "register": "formal-military"},
        {"term": "encryption", "definition": "cifrado", "register": "formal-military"},
        {"term": "decryption", "definition": "descifrado", "register": "formal-military"},
        {"term": "backdoor", "definition": "puerta trasera", "register": "formal-military"},
        {"term": "supply chain attack", "definition": "ataque a la cadena de suministro", "register": "formal-military"},
        {"term": "social engineering", "definition": "ingeniería social", "register": "formal-military"},
        {"term": "threat actor", "definition": "actor de amenaza", "register": "formal-military"},
        {"term": "attribution", "definition": "atribución", "register": "formal-military"},
        {"term": "incident response", "definition": "respuesta a incidentes", "register": "formal-military"},
        {"term": "forensics", "definition": "informática forense", "register": "formal-military"},
        {"term": "vulnerability assessment", "definition": "evaluación de vulnerabilidades", "register": "formal-military"},
        {"term": "penetration testing", "definition": "pruebas de penetración", "register": "formal-military"},
        {"term": "critical infrastructure", "definition": "infraestructura crítica", "register": "formal-military"},
        {"term": "air gap", "definition": "separación física de red", "register": "formal-military"},
        {"term": "insider threat", "definition": "amenaza interna", "register": "formal-military"},
        {"term": "offensive cyber operation", "definition": "operación cibernética ofensiva", "register": "formal-military"},
        {"term": "defensive cyber operation", "definition": "operación cibernética defensiva", "register": "formal-military"},
        {"term": "cyber resilience", "definition": "resiliencia cibernética", "register": "formal-military"},
        {"term": "nation-state actor", "definition": "actor estatal", "register": "formal-military"},
    ],
}


# ---------------------------------------------------------------------------
# Direction dispatcher
# ---------------------------------------------------------------------------
# `seed_topic_for_learner` consults this map to pick the right seed
# set for the (source_lang, target_lang) of the learner's session.
# Reverse direction (e.g. ko→en, es→en) is handled by callers swapping
# `term` and `definition` at lookup time; no duplicate data needed.

_SEED_SETS: dict[tuple[str, str], dict[str, list[dict]]] = {
    ("en", "ko"): TOPIC_SEEDS,
    ("en", "es"): EN_ES_TOPIC_SEEDS,
}


def seed_set_for_direction(
    source_lang: str, target_lang: str
) -> tuple[dict[str, list[dict]], bool]:
    """Resolve the (seed dict, needs_swap) tuple for a direction.

    Returns the dict whose entries have `term` in the canonical source
    language and `definition` in the target. `needs_swap` is True when
    the caller is asking for the REVERSE of the canonical seed direction
    (e.g. asking for ko→en when only en→ko is seeded) — the caller
    should treat `term` as the target and `definition` as the source.

    Returns `({}, False)` if no seed set exists for this direction; the
    learner will fall back to extraction-based vocab discovery.
    """
    canonical = _SEED_SETS.get((source_lang, target_lang))
    if canonical is not None:
        return canonical, False
    reverse = _SEED_SETS.get((target_lang, source_lang))
    if reverse is not None:
        return reverse, True
    return {}, False


def seed_uuid(domain: str, source_lang: str, term: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"vocab_seed:{domain}:{source_lang}:{term}")


def domain_asr_prompt(domain: str, target_lang: str) -> str:
    """Return a comma-joined hint string of domain vocabulary for Whisper
    priming.

    Uses whichever seed set has entries for the requested target. For
    `ko` the Korean definitions of TOPIC_SEEDS are used; for `es` the
    Spanish definitions of EN_ES_TOPIC_SEEDS (when populated); the
    fallback is the canonical English terms in TOPIC_SEEDS. Unknown
    domains return an empty string.
    """
    if target_lang == "ko":
        entries = TOPIC_SEEDS.get(domain) or []
        return ", ".join(e["definition"] for e in entries)
    if target_lang == "es":
        entries = EN_ES_TOPIC_SEEDS.get(domain) or []
        if entries:
            return ", ".join(e["definition"] for e in entries)
        # Fallback to English terms — gives Whisper SOME priming hint
        # for the es pair before the seed generator has run.
        entries = TOPIC_SEEDS.get(domain) or []
        return ", ".join(e["term"] for e in entries)
    # Default (en or other): the English terms from TOPIC_SEEDS.
    entries = TOPIC_SEEDS.get(domain) or []
    return ", ".join(e["term"] for e in entries)
