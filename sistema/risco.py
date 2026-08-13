"""
Regra que classifica o risco de evasão de cada atleta.

Essa foi a parte mais difícil do projeto e também a mais importante, então
deixei num arquivo separado. Assim eu consigo testar a regra sozinha, sem
precisar subir o site inteiro, e fica mais fácil de explicar na apresentação.

A ideia saiu da conversa com a coordenação: hoje eles só descobrem que uma
criança parou de vir quando alguém comenta no treino, e isso leva uns dois
meses. Eu queria que o sistema avisasse em uma semana.
"""

from dataclasses import dataclass
from datetime import date
from typing import Literal, Optional, Sequence

StatusPresenca = Literal["presente", "falta", "justificada"]
NivelRisco = Literal["regular", "atencao", "risco", "evadido"]

# Janela que eu uso pra calcular a frequência, em dias.
JANELA_DIAS = 30

# Passando disso sem nenhuma presença, eu considero que a criança evadiu.
DIAS_PARA_EVASAO = 30

# Esses números eu não inventei nem tirei de fórmula nenhuma. Peguei olhando o
# caderno de chamada da escolinha junto com o coordenador: era mais ou menos
# assim que ele já fazia de cabeça pra decidir de quem ia atrás.
LIMITE_FREQUENCIA_ATENCAO = 0.75
LIMITE_FREQUENCIA_RISCO = 0.50
FALTAS_CONSECUTIVAS_ATENCAO = 2
FALTAS_CONSECUTIVAS_RISCO = 3


@dataclass(frozen=True)
class RegistroPresenca:
    data: date
    status: StatusPresenca


@dataclass(frozen=True)
class AvaliacaoRisco:
    nivel: NivelRisco
    # Fica None quando não teve nenhum treino no período, senão eu dividiria
    # por zero e o sistema quebrava.
    frequencia: Optional[float]
    faltas_consecutivas: int
    dias_desde_ultima_presenca: Optional[int]
    treinos_na_janela: int
    motivo: str

    @property
    def frequencia_pct(self) -> Optional[int]:
        return None if self.frequencia is None else round(self.frequencia * 100)


def _contar_faltas_consecutivas(ordenados: Sequence[RegistroPresenca]) -> int:
    """
    Conta quantas faltas seguidas o atleta tem, olhando de trás pra frente.

    Falta justificada eu pulo: ela não zera a contagem, mas também não soma.
    Se a mãe avisou que a criança está doente, isso não quer dizer que ela vai
    largar a escolinha.
    """
    total = 0
    for registro in reversed(ordenados):
        if registro.status == "presente":
            break
        if registro.status == "falta":
            total += 1
    return total


def avaliar_risco(
    presencas: Sequence[RegistroPresenca],
    referencia: Optional[date] = None,
) -> AvaliacaoRisco:
    if referencia is None:
        referencia = date.today()

    ordenados = sorted(
        (p for p in presencas if p.data <= referencia),
        key=lambda p: p.data,
    )

    ultima_presenca = next(
        (p for p in reversed(ordenados) if p.status == "presente"), None
    )
    dias_desde_ultima = (
        (referencia - ultima_presenca.data).days if ultima_presenca else None
    )

    inicio_janela = date.fromordinal(referencia.toordinal() - JANELA_DIAS)
    na_janela = [p for p in ordenados if p.data >= inicio_janela]

    # Justificada fica fora da conta dos dois lados: não entra como presença
    # nem como falta. Se eu contasse como falta, criança doente ia aparecer
    # como risco de evasão, e não é isso que está acontecendo com ela.
    presentes = sum(1 for p in na_janela if p.status == "presente")
    faltas = sum(1 for p in na_janela if p.status == "falta")
    base = presentes + faltas
    frequencia = (presentes / base) if base > 0 else None

    faltas_consecutivas = _contar_faltas_consecutivas(ordenados)

    def montar(nivel: NivelRisco, motivo: str) -> AvaliacaoRisco:
        return AvaliacaoRisco(
            nivel=nivel,
            frequencia=frequencia,
            faltas_consecutivas=faltas_consecutivas,
            dias_desde_ultima_presenca=dias_desde_ultima,
            treinos_na_janela=len(na_janela),
            motivo=motivo,
        )

    # A ordem desses ifs importa. Eu testo do caso mais grave pro mais leve,
    # porque quem evadiu também bate na regra de "atenção", e se eu testasse
    # atenção primeiro ele nunca ia ser classificado como evadido.

    if dias_desde_ultima is None:
        return montar("evadido", "Nunca registrou presença desde a matrícula")

    if dias_desde_ultima > DIAS_PARA_EVASAO:
        return montar("evadido", f"Sem presença há {dias_desde_ultima} dias")

    if faltas_consecutivas >= FALTAS_CONSECUTIVAS_RISCO:
        return montar("risco", f"{faltas_consecutivas} faltas seguidas")

    if frequencia is not None and frequencia < LIMITE_FREQUENCIA_RISCO:
        return montar(
            "risco",
            f"Frequência de {round(frequencia * 100)}% nos últimos {JANELA_DIAS} dias",
        )

    if faltas_consecutivas >= FALTAS_CONSECUTIVAS_ATENCAO:
        return montar("atencao", f"{faltas_consecutivas} faltas seguidas")

    if frequencia is not None and frequencia < LIMITE_FREQUENCIA_ATENCAO:
        return montar(
            "atencao",
            f"Frequência de {round(frequencia * 100)}% nos últimos {JANELA_DIAS} dias",
        )

    if frequencia is None:
        return montar("regular", "Sem treinos registrados no período")

    return montar(
        "regular",
        f"Frequência de {round(frequencia * 100)}% nos últimos {JANELA_DIAS} dias",
    )


ROTULO_RISCO: dict[str, str] = {
    "regular": "Regular",
    "atencao": "Atenção",
    "risco": "Risco de evasão",
    "evadido": "Evadido",
}

# Uso isso pra ordenar a lista de contato. Botei "risco" na frente de
# "evadido" de propósito: quem está sumindo agora ainda dá pra segurar, quem
# já sumiu faz três meses é mais difícil de trazer de volta.
PRIORIDADE_RISCO: dict[str, int] = {
    "risco": 0,
    "evadido": 1,
    "atencao": 2,
    "regular": 3,
}
