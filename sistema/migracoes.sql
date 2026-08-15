-- O que passou a existir DEPOIS do schema original.
--
-- Por que este arquivo existe em vez de eu simplesmente acrescentar as tabelas
-- no schema.sql: o schema.sql começa com DROP TABLE. Rodar ele num banco em uso
-- apaga o cadastro inteiro. Enquanto o sistema só rodava com base de
-- demonstração isso não doía — era só reconfigurar e reimportar as planilhas.
-- No computador do Centro dói, porque lá tem chamada digitada na tela que não
-- está em planilha nenhuma. Se atualizar o sistema custasse o semestre de
-- presença, ninguém atualizaria.
--
-- Então tudo aqui é ADITIVO e idempotente (IF NOT EXISTS), e roda toda vez que
-- o sistema sobe. Quando o banco já está em dia o SQLite resolve isso em
-- microssegundos.
--
-- Regra pra quem mexer aqui depois: nada de DROP, nada de DELETE, nada que
-- reescreva linha existente. Só criar o que falta.

-- O PLANO DE TREINO: o que vai ser feito no treino do dia.
--
-- Faltava a resposta da pergunta que o atleta mais faz — "o que a gente vai
-- treinar hoje?". O sistema sabia quem estava matriculado, quem faltou e quem
-- foi convocado, mas o conteúdo do treino só existia na cabeça do professor.
--
-- A forma copia a da tabela evento de propósito: modalidade obrigatória, turma
-- opcional. Turma nula é plano da modalidade inteira; turma preenchida é plano
-- só daquele grupo — o Sub-11 não precisa ler o treino tático do Sub-17.
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
