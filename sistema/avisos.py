"""
Avisos pros participantes: evento marcado, plano publicado, horário novo.

O sistema registra sozinho — a coordenação não escreve aviso nenhum. Quem tem
e-mail na ficha também recebe por lá, quando o correio está configurado.
"""

import correio


def registrar(conexao, modalidade_id: int, turma_id, titulo: str, corpo: str) -> None:
    conexao.execute(
        "INSERT INTO aviso (modalidade_id, turma_id, titulo, corpo) VALUES (?,?,?,?)",
        (modalidade_id, turma_id, titulo, corpo),
    )
    conexao.commit()

    if not correio.configurado():
        return
    destinos = conexao.execute(
        """
        SELECT DISTINCT p.email
        FROM pessoa p
        JOIN matricula ma ON ma.pessoa_id = p.id AND ma.status = 'ativa'
        JOIN turma t ON t.id = ma.turma_id
        WHERE t.modalidade_id = ? AND (? IS NULL OR ma.turma_id = ?)
          AND p.email IS NOT NULL
        """,
        (modalidade_id, turma_id, turma_id),
    ).fetchall()
    correio.enviar_em_lote([(d["email"], titulo, corpo) for d in destinos])


def da_pessoa(conexao, pessoa_id: int, limite: int = 10) -> list[dict]:
    """Os avisos das turmas ativas da pessoa, mais novos primeiro."""
    avisos = [dict(l) for l in conexao.execute(
        """
        SELECT a.*, m.nome AS modalidade_nome, t.nome AS turma_nome
        FROM aviso a
        JOIN modalidade m ON m.id = a.modalidade_id
        LEFT JOIN turma t ON t.id = a.turma_id
        WHERE EXISTS (
            SELECT 1 FROM matricula ma
            JOIN turma tu ON tu.id = ma.turma_id
            WHERE ma.pessoa_id = ? AND ma.status = 'ativa'
              AND tu.modalidade_id = a.modalidade_id
              AND (a.turma_id IS NULL OR a.turma_id = ma.turma_id)
        )
        ORDER BY a.id DESC LIMIT ?
        """,
        (pessoa_id, limite),
    )]
    for a in avisos:
        criado = a["criado_em"]
        a["quando"] = f"{criado[8:10]}/{criado[5:7]} às {criado[11:16]}"
    return avisos
