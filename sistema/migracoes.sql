-- O que passou a existir DEPOIS do schema original.
--
-- Não pus estas tabelas no schema.sql porque ele começa com DROP TABLE: rodar
-- ele num banco em uso apaga tudo. Com a base de demonstração isso não doía,
-- era só reimportar as planilhas. No computador do Centro dói, porque lá tem
-- chamada digitada na tela que não está em planilha nenhuma.
--
-- Tudo aqui é aditivo e usa IF NOT EXISTS, então roda a cada início sem
-- problema. Regra pra mim mesmo no futuro: nada de DROP nem DELETE aqui.

-- O PLANO DE TREINO: o que vai ser feito no treino do dia.
--
-- O sistema sabia quem estava matriculado, quem faltou e quem foi convocado,
-- mas não respondia "o que a gente vai treinar hoje?". Isso só existia no
-- caderno do professor.
--
-- Copiei a forma da tabela evento: modalidade obrigatória, turma opcional.
-- Turma nula vale pra modalidade inteira; preenchida esconde das outras,
-- porque o Sub-11 não precisa ler o treino tático do Sub-17.
CREATE TABLE IF NOT EXISTS plano_treino (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    modalidade_id  INTEGER NOT NULL REFERENCES modalidade (id) ON DELETE CASCADE,
    turma_id       INTEGER          REFERENCES turma (id) ON DELETE SET NULL,

    data           DATE    NOT NULL,
    titulo         TEXT    NOT NULL,

    -- Texto corrido, escrito pelo professor. Não é lista de exercício
    -- estruturada, e isso é decisão: ele já escreve o treino num caderno em
    -- frase solta, e obrigar a preencher campo por campo faria ele parar de
    -- usar. O sistema aceita como ele escreve.
    conteudo       TEXT    NOT NULL,

    -- O que levar: caneleira, bola, garrafa de água. Fica separado do conteúdo
    -- porque é o que o atleta precisa ler ANTES de sair de casa, e no meio de
    -- um parágrafo de tática isso se perde.
    material       TEXT,

    criado_em      TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_plano_data       ON plano_treino (data);
CREATE INDEX IF NOT EXISTS idx_plano_modalidade ON plano_treino (modalidade_id);
