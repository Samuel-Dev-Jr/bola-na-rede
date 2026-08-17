# Centro de Cultura e Esportes — sistema de gestão

Sistema web que substitui as folhas de presença em papel do Centro de Cultura e
Esportes, no Jardim Elizabete, em Taboão da Serra/SP. Ele registra cadastro,
chamada e frequência, e avisa a coordenação quando uma criança está deixando de
aparecer — que era o problema que originou o projeto.

Escrito por mim, Samuel Sousa Nunes, como Projeto de Extensão Curricularizada do
curso de Análise e Desenvolvimento de Sistemas da UniFECAF, em 2026.

## Situação do projeto

**Entregue e funcionando, com o desenvolvimento em pausa por decisão de projeto.**

Apresentei o sistema aos professores do Centro em 15/08/2026 e eles aprovaram
num primeiro momento. Ficou combinado que usariam a ferramenta durante a semana
seguinte, junto com os outros orientadores, e me trariam o retorno: o que
faltou, o que atrapalhou e o que precisa mudar.

Estou aguardando esse retorno para continuar. A decisão é deliberada — a
primeira solução que propus a eles, uma planilha de controle, foi recusada
justamente porque eu tinha desenhado sozinho o que achava que resolveria. Não
pretendo repetir o erro construindo mais funcionalidade antes de saber o que o
uso real mostrou.

O que já está definido para a próxima etapa depende do que vier deles. O que eu
já sei que ficou de fora está listado em
[sistema/README.md](sistema/README.md#o-que-ficou-de-fora) e
[sistema/DECISOES.md](sistema/DECISOES.md).

## Ver funcionando

**https://bola-na-rede.onrender.com**

O sistema exige login. **As credenciais de demonstração não ficam neste
repositório** — eu as entrego diretamente a quem precisa avaliar o projeto.
Senha escrita em arquivo versionado é senha pública, mesmo em repositório
privado: basta o acesso mudar uma vez para ela deixar de ser segredo, e o git
guarda para sempre o que entra.

A conta de demonstração enxerga apenas a base de exibição — 62 pessoas com
dados inventados, chamada e jogos de exemplo. Ela não dá acesso a informação
de ninguém do Centro. Pode-se clicar em tudo: o que for digitado ali se apaga
no reinício seguinte.

Duas ressalvas da hospedagem gratuita: a instância **hiberna** depois de uns 15
minutos parada e leva perto de um minuto para acordar, então abra o link uma vez
antes de mostrar para alguém. E o endereço manteve o nome antigo do projeto de
propósito — trocá-lo derrubaria o link já divulgado.

## O que o sistema faz

- **Cadastro e ficha** — dados da pessoa, responsável, contato de emergência e
  informações de saúde, com a pessoa separada da matrícula: quem faz futsal e
  jiu-jitsu é uma pessoa só, não duas.
- **Chamada e frequência** — lançamento por treino e o percentual somado por
  atividade, que no papel ninguém calculava.
- **Risco de evasão** — classifica cada matrícula pela sequência de faltas e
  pela frequência dos últimos 30 dias, e monta a lista de quem ligar na semana,
  com o telefone do responsável.
- **Agenda, convocação e escalação** — jogos, quem foi convocado e o time em
  campo, com a mensagem pronta para o grupo de WhatsApp.
- **Plano de treino e avisos** — o que vai ser treinado, visível para quem
  participa.
- **Área do participante** — horário, frequência, avisos e convocação, no
  celular, sem precisar perguntar para ninguém.

## Como rodar

Python 3.13, Flask e SQLite em arquivo único. Sem Node, sem servidor de banco e
sem internet — o técnico usa na beira da quadra, onde às vezes não pega sinal.

```bash
pip install -r sistema/requirements.txt
python sistema/configurar.py      # cria o banco com as modalidades e turmas
python sistema/criar_usuario.py   # cria o primeiro acesso
python sistema/app.py             # abre em http://localhost:5000
```

No Windows, `sistema/iniciar.bat` faz o mesmo com dois cliques.

As instruções completas — importação de planilha, papéis de acesso, deploy e a
regra de risco em detalhe — estão em **[sistema/README.md](sistema/README.md)**.
O porquê de cada decisão está em **[sistema/DECISOES.md](sistema/DECISOES.md)**.

## O que este repositório NÃO contém

Isso aqui é escolha de projeto, não esquecimento:

- **O banco de dados.** Se a coordenação usar o sistema para valer, o arquivo
  passa a conter nome de criança, telefone de responsável e ficha médica.
  Commitar isso publicaria dado sensível de menor de idade, e o git guarda para
  sempre o que entra uma vez — apagar depois não desfaz.
- **Fotos, prints e o caderno de campo.** São entregáveis da faculdade e
  contêm imagens de pessoas do Centro.
- **A carta de recomendação preenchida**, que traz nome e documento de gente da
  coordenação.
- **Senha de administrador.** O `render.yaml` deixa `ADMIN_SENHA` sem valor de
  propósito, para a hospedagem pedir na primeira publicação. Senha escrita em
  arquivo versionado é senha pública.

A instância hospedada nunca recebe o caderno real do Centro. Dado de criança
fica na rede local, no computador de lá.
