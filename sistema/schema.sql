-- Banco do Projeto Social Bola na Rede
-- Extensão Curricularizada UniFECAF / Análise e Desenvolvimento de Sistemas
--
-- A tabela mensalidade eu TIREI de propósito. O projeto é um grupo comunitário
-- informal, sem CNPJ, e as atividades são gratuitas. Um sistema que controla
-- cobrança daria a entender que existe pessoa jurídica por trás, e não existe.
--
-- A mudança mais importante do banco foi separar PESSOA de MATRÍCULA.
-- Na primeira versão cada linha de aluno pertencia a uma modalidade só. Só que
-- metade das crianças do Centro faz mais de uma atividade: o Samuel joga
-- futebol e basquete, a Cris faz vôlei e karatê. Do jeito antigo, o Samuel
-- virava duas pessoas no banco, com telefone repetido e a ficha médica
-- preenchida em uma e vazia na outra. Era exatamente o problema do caderno de
-- papel, que eu tinha copiado sem perceber.
--
-- Agora pessoa e turma se ligam por matricula, que é uma tabela associativa.
-- A presença passa a ser da matrícula, não da pessoa, porque a frequência é
-- por modalidade: dá pra ser assíduo no futebol e estar sumindo do basquete.

PRAGMA foreign_keys = ON;

-- A ordem importa: só dá pra apagar uma tabela depois de apagar as que
-- apontam pra ela.
DROP TABLE IF EXISTS convocacao;
DROP TABLE IF EXISTS evento;
DROP TABLE IF EXISTS presenca;
DROP TABLE IF EXISTS matricula;

-- Tabelas de versões antigas do banco. Se eu não apagar essas aqui, quem já
-- tinha rodado a versão anterior toma erro de chave estrangeira ao recriar,
-- porque a antiga "atleta" ainda aponta pra "turma". Descobri rodando o seed
-- por cima de um banco velho.
DROP TABLE IF EXISTS mensalidade;
DROP TABLE IF EXISTS atleta;

-- usuario aponta pra pessoa, então cai antes dela.
DROP TABLE IF EXISTS usuario;

DROP TABLE IF EXISTS pessoa;
DROP TABLE IF EXISTS turma;
DROP TABLE IF EXISTS modalidade;

-- As atividades do Centro. Futebol, vôlei e basquete aparecem duas vezes cada,
-- uma no masculino e outra no feminino, porque competem em categorias
-- separadas e treinam em dias diferentes. Karatê e pilates são mistos.
CREATE TABLE modalidade (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    slug            TEXT    NOT NULL UNIQUE,
    nome            TEXT    NOT NULL,
    genero          TEXT    NOT NULL CHECK (genero IN ('Masculino','Feminino','Misto')),
    descricao       TEXT    NOT NULL,

    -- A cor é do esporte, não do gênero. Futebol masculino e feminino usam o
    -- mesmo verde e se diferenciam pela faixa listrada no cartão.
    cor             TEXT    NOT NULL,
    icone           TEXT    NOT NULL,

    -- Dias da semana com aula, no formato "0,2,4" (0 = segunda).
    dias_aula       TEXT    NOT NULL,
    horario         TEXT    NOT NULL,

    tem_convocacao  INTEGER NOT NULL DEFAULT 1 CHECK (tem_convocacao IN (0,1)),

    -- Como cada modalidade chama as coisas, pra eu não escrever "treino" na
    -- tela do pilates. O artigo entra junto porque senão sai "uma treino".
    termo_aluno     TEXT    NOT NULL DEFAULT 'atleta',
    termo_aula      TEXT    NOT NULL DEFAULT 'treino',
    termo_aula_pl   TEXT    NOT NULL DEFAULT 'treinos',
    artigo_aula     TEXT    NOT NULL DEFAULT 'um',

    ordem           INTEGER NOT NULL DEFAULT 0
);

-- As turmas de cada modalidade: categorias por idade no futebol, faixas no
-- karatê, horários no pilates.
CREATE TABLE turma (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    modalidade_id  INTEGER NOT NULL REFERENCES modalidade (id) ON DELETE CASCADE,
    nome           TEXT    NOT NULL,
    ordem          INTEGER NOT NULL DEFAULT 0,

    UNIQUE (modalidade_id, nome)
);

-- A PESSOA. Uma linha por ser humano, não importa em quantas atividades ele
-- esteja. É aqui que mora a ficha médica, e é isso que resolve o problema de
-- a alergia estar anotada só no caderno do futebol.
CREATE TABLE pessoa (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    nome                    TEXT    NOT NULL,
    data_nascimento         DATE    NOT NULL,

    responsavel_nome        TEXT    NOT NULL,
    responsavel_parentesco  TEXT    NOT NULL,
    responsavel_telefone    TEXT    NOT NULL,

    emergencia_nome         TEXT,
    emergencia_telefone     TEXT,

    alergias                TEXT,
    condicoes               TEXT,
    medicacao_continua      TEXT,
    plano_saude             TEXT,
    observacoes_medicas     TEXT,

    autoriza_imagem         INTEGER NOT NULL DEFAULT 0 CHECK (autoriza_imagem IN (0,1)),

    criado_em               TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    atualizado_em           TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

-- A MATRÍCULA liga uma pessoa a uma turma. É a tabela associativa que permite
-- o mesmo aluno estar em duas modalidades sem duplicar o cadastro.
CREATE TABLE matricula (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    pessoa_id      INTEGER NOT NULL REFERENCES pessoa (id) ON DELETE CASCADE,
    turma_id       INTEGER NOT NULL REFERENCES turma (id) ON DELETE CASCADE,
    data_matricula DATE    NOT NULL,
    status         TEXT    NOT NULL DEFAULT 'ativa' CHECK (status IN ('ativa','encerrada')),

    -- O número da camisa fica na MATRÍCULA, não na pessoa: ele é do time, não
    -- do ser humano. A mesma criança pode ser 10 no futebol e 7 no basquete, e
    -- no karatê não usar número nenhum.
    numero         INTEGER CHECK (numero IS NULL OR numero BETWEEN 1 AND 99),

    -- A mesma pessoa não pode estar duas vezes na mesma turma.
    UNIQUE (pessoa_id, turma_id)
);

CREATE INDEX idx_matricula_pessoa ON matricula (pessoa_id);
CREATE INDEX idx_matricula_turma  ON matricula (turma_id);

-- Duas camisas iguais na mesma turma, não. Em turmas diferentes, sim: o Sub-13
-- pode ter um 10 sem impedir o Sub-15 de ter outro.
--
-- O índice é PARCIAL (o WHERE no fim) porque a maioria das matrículas não tem
-- número. Sem o WHERE, o segundo NULL já seria recusado como repetido.
CREATE UNIQUE INDEX idx_matricula_numero
    ON matricula (turma_id, numero) WHERE numero IS NOT NULL;

-- Presença numa aula. Aponta pra matrícula e não pra pessoa, porque a
-- frequência é por modalidade: dá pra ser assíduo no futebol e estar sumindo
-- do basquete ao mesmo tempo.
CREATE TABLE presenca (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    matricula_id INTEGER NOT NULL REFERENCES matricula (id) ON DELETE CASCADE,
    data         DATE    NOT NULL,
    status       TEXT    NOT NULL CHECK (status IN ('presente','falta','justificada')),

    UNIQUE (matricula_id, data)
);

CREATE INDEX idx_presenca_data      ON presenca (data);
CREATE INDEX idx_presenca_matricula ON presenca (matricula_id);

-- Jogo, torneio ou amistoso. Só as modalidades coletivas usam.
CREATE TABLE evento (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    modalidade_id  INTEGER NOT NULL REFERENCES modalidade (id) ON DELETE CASCADE,
    turma_id       INTEGER          REFERENCES turma (id) ON DELETE SET NULL,
    nome           TEXT    NOT NULL,
    adversario     TEXT,
    data           DATE    NOT NULL,
    local          TEXT    NOT NULL,
    observacoes    TEXT,
    criado_em      TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE INDEX idx_evento_data       ON evento (data);
CREATE INDEX idx_evento_modalidade ON evento (modalidade_id);

CREATE TABLE convocacao (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    evento_id    INTEGER NOT NULL REFERENCES evento (id) ON DELETE CASCADE,
    matricula_id INTEGER NOT NULL REFERENCES matricula (id) ON DELETE CASCADE,

    UNIQUE (evento_id, matricula_id)
);

-- O USUÁRIO. Esta tabela só passou a existir quando o sistema saiu de "roda na
-- rede local e todo mundo vê tudo" para "cada um entra com o seu login". Ver a
-- seção 4 do DECISOES.md: a ausência de login era a maior lacuna do projeto.
--
-- Guardo hash da senha, nunca a senha. O hash é gerado pelo werkzeug, que já
-- vem com o Flask, com sal por senha — então duas pessoas com a mesma senha
-- ficam com hashes diferentes.
CREATE TABLE usuario (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,

    -- COLLATE NOCASE porque "Samuel" e "samuel" tem que ser o MESMO usuário.
    -- Sem isso dava pra criar duas contas que a coordenação leria como uma.
    login         TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    senha_hash    TEXT    NOT NULL,

    papel         TEXT    NOT NULL CHECK (papel IN ('admin','jogador')),

    -- Aponta pra pessoa quando o usuário é um participante do Centro. Fica nulo
    -- para quem administra e não é aluno — o coordenador, por exemplo. É esta
    -- coluna que faz a área do jogador mostrar só as atividades dele: ela chega
    -- na matrícula pela pessoa, e a matrícula é que tem frequência e convocação.
    pessoa_id     INTEGER REFERENCES pessoa (id) ON DELETE SET NULL,

    -- Desativar em vez de apagar: apagar perderia o histórico de quem era.
    ativo         INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0,1)),

    criado_em     TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    ultimo_acesso TEXT
);

CREATE INDEX idx_usuario_pessoa ON usuario (pessoa_id);
