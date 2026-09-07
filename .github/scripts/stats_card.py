"""Gera os SVGs dos cards de estatistica e de linguagens mais usadas.

Substitui o github-readme-stats.vercel.app: a instancia publica vive
respondendo 503/429 por estourar a cota do Vercel, e a alternativa era
manter um fork proprio hospedado. Aqui o SVG e gerado por Action e
commitado na branch "output", entao nao depende de servico externo.

Uso: python stats_card.py <usuario> <saida-stats.svg> <saida-langs.svg>
     precisa da env var GITHUB_TOKEN

Sobre repositorio privado: o GITHUB_TOKEN padrao do Actions so enxerga o
que e publico. Para contar commit e linguagem de repo privado, criar um
Personal Access Token classico com escopo "repo", salvar como secret
STATS_TOKEN e o workflow ja o usa no lugar do token padrao.
"""

import json
import os
import subprocess
import sys

# Paleta tokyo night, a mesma dos outros SVGs deste repositorio.
BG = "#1a1b26"
TITLE = "#7aa2f7"
TEXT = "#c0caf5"
ACCENT = "#7dcfff"
MUTED = "#565f89"

FONTE = "Segoe UI, Ubuntu, sans-serif"

QUERY = """
{
  user(login: "%s") {
    name
    followers { totalCount }
    contributionsCollection {
      totalCommitContributions
      restrictedContributionsCount
      totalPullRequestContributions
      totalIssueContributions
      totalRepositoriesWithContributedCommits
    }
    # Estrelas: so o que e seu mesmo. Repo da organizacao nao entra, as
    # estrelas dele nao sao suas.
    proprios: repositories(first: 100, ownerAffiliations: OWNER, isFork: false) {
      totalCount
      nodes { stargazerCount }
    }
    # Linguagens: aqui a org ENTRA. O trabalho profissional vive em
    # tecnosuporte/*, e sem isso o card mede so os projetos de estudo
    # antigos e mostra um stack que nao e o seu.
    paraLinguagem: repositories(
      first: 100
      ownerAffiliations: [OWNER, ORGANIZATION_MEMBER]
      isFork: false
    ) {
      nodes {
        languages(first: 10, orderBy: { field: SIZE, direction: DESC }) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""


def consulta(usuario):
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("erro: falta a env var GITHUB_TOKEN")

    req = json.dumps({"query": QUERY % usuario}).encode()
    saida = subprocess.run(
        ["curl", "-sS", "-X", "POST",
         "-H", f"Authorization: bearer {token}",
         "-H", "Content-Type: application/json",
         "--data-binary", "@-",
         "https://api.github.com/graphql"],
        input=req, capture_output=True, check=True,
    ).stdout

    dados = json.loads(saida)
    if "errors" in dados:
        sys.exit(f"erro da API: {dados['errors']}")
    return dados["data"]["user"]


def num(n):
    """1234 -> '1.234' (separador de milhar em pt-BR)."""
    return f"{n:,}".replace(",", ".")


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def card_stats(user, usuario, destino):
    c = user["contributionsCollection"]
    # restrictedContributionsCount = commits em repo privado; so vem
    # preenchido quando o token tem escopo para enxergar
    commits = c["totalCommitContributions"] + c["restrictedContributionsCount"]
    estrelas = sum(r["stargazerCount"] for r in user["proprios"]["nodes"])

    linhas = [
        ("Commits no ano", num(commits)),
        ("Pull requests", num(c["totalPullRequestContributions"])),
        ("Issues", num(c["totalIssueContributions"])),
        ("Repositórios com contribuição", num(c["totalRepositoriesWithContributedCommits"])),
        ("Estrelas recebidas", num(estrelas)),
        ("Seguidores", num(user["followers"]["totalCount"])),
    ]

    nome = user.get("name") or usuario
    W, H = 480, 195
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'viewBox="0 0 {W} {H}" font-family="{FONTE}" role="img" '
         f'aria-label="Estatísticas de {esc(nome)} no GitHub">',
         f'<rect width="{W}" height="{H}" rx="16" fill="{BG}"/>',
         f'<text x="25" y="35" fill="{TITLE}" font-size="16" font-weight="600">'
         f'Estatísticas de {esc(nome)}</text>']

    y = 68
    for rotulo, valor in linhas:
        p.append(f'<text x="25" y="{y}" fill="{TEXT}" font-size="13">{esc(rotulo)}</text>')
        p.append(f'<text x="{W - 25}" y="{y}" fill="{ACCENT}" font-size="13" '
                 f'font-weight="700" text-anchor="end">{valor}</text>')
        y += 21

    p.append("</svg>")
    escreve(destino, "\n".join(p))


def card_langs(user, destino, quantidade=8):
    """Barra empilhada com as linguagens mais usadas, por bytes de codigo."""
    total_por_lang = {}
    cores = {}
    for repo in user["paraLinguagem"]["nodes"]:
        for e in repo["languages"]["edges"]:
            nome = e["node"]["name"]
            total_por_lang[nome] = total_por_lang.get(nome, 0) + e["size"]
            cores[nome] = e["node"]["color"] or ACCENT

    ranking = sorted(total_por_lang.items(), key=lambda kv: kv[1], reverse=True)[:quantidade]
    total = sum(v for _, v in ranking) or 1
    # Tira o que arredonda para 0.0%: linguagem com meia duzia de linhas
    # aparecia na legenda zerada, o que so suja o card.
    ranking = [(n, t) for n, t in ranking if 100 * t / total >= 0.05]

    W, H = 340, 195
    BARRA_X, BARRA_Y, BARRA_W, BARRA_H = 25, 55, W - 50, 10

    p = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'viewBox="0 0 {W} {H}" font-family="{FONTE}" role="img" '
         f'aria-label="Linguagens mais usadas">',
         f'<rect width="{W}" height="{H}" rx="16" fill="{BG}"/>',
         f'<text x="25" y="35" fill="{TITLE}" font-size="16" font-weight="600">Tecnologias</text>']

    if not ranking:
        p.append(f'<text x="25" y="70" fill="{MUTED}" font-size="13">sem dados públicos</text>')
        p.append("</svg>")
        escreve(destino, "\n".join(p))
        return

    # barra empilhada: cada linguagem ocupa a fatia proporcional aos bytes
    x = BARRA_X
    p.append(f'<clipPath id="barra"><rect x="{BARRA_X}" y="{BARRA_Y}" '
             f'width="{BARRA_W}" height="{BARRA_H}" rx="5"/></clipPath>')
    p.append('<g clip-path="url(#barra)">')
    for nome, tamanho in ranking:
        w = BARRA_W * tamanho / total
        p.append(f'<rect x="{x:.2f}" y="{BARRA_Y}" width="{w:.2f}" '
                 f'height="{BARRA_H}" fill="{cores[nome]}"/>')
        x += w
    p.append("</g>")

    # legenda em duas colunas
    for i, (nome, tamanho) in enumerate(ranking):
        col, linha = i % 2, i // 2
        lx = 25 + col * 155
        ly = 95 + linha * 24
        pct = 100 * tamanho / total
        p.append(f'<circle cx="{lx + 5}" cy="{ly - 4}" r="5" fill="{cores[nome]}"/>')
        p.append(f'<text x="{lx + 18}" y="{ly}" fill="{TEXT}" font-size="12">'
                 f'{esc(nome)} <tspan fill="{MUTED}">{pct:.1f}%</tspan></text>')

    p.append("</svg>")
    escreve(destino, "\n".join(p))


def escreve(destino, conteudo):
    os.makedirs(os.path.dirname(destino) or ".", exist_ok=True)
    with open(destino, "w", encoding="utf-8") as f:
        f.write(conteudo)
    print(f"gerado: {destino}")


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    usuario, saida_stats, saida_langs = sys.argv[1:4]
    user = consulta(usuario)
    card_stats(user, usuario, saida_stats)
    card_langs(user, saida_langs)


if __name__ == "__main__":
    main()
