"""
Auditoria reproduzível dos CSVs, sem modificar dados raw.

Execute na raiz: python -m src.auditoria
Para guardar o relatório: python -m src.auditoria --saida data/auditoria.log
"""

import argparse
from datetime import datetime
from pathlib import Path
import sys

import pandas as pd

from src import config, limpeza


COLUNAS_TEXTO = {
    "compras": ["razao_social_orgao", "uf_sigla", "uf_nome", "objeto_compra"],
    "itens": ["descricao", "material_ou_servico"],
    "resultados": ["nome_fornecedor", "porte"],
}
COLUNAS_NUMERO = {
    "itens": ["quantidade", "valor_unitario_estimado"],
    "resultados": ["quantidade_homologada", "valor_unitario_homologado"],
}
COLUNAS_DATA = {"compras": "data_publicacao", "resultados": "data_resultado"}
CHAVE_ITEM = ["numero_controle_pncp", "numero_item"]


def ler_bases():
    return {
        nome: pd.read_csv(
            config.PASTA_RAW / f"{nome}.csv",
            dtype=str, keep_default_na=False, encoding="utf-8-sig",
        )
        for nome in ("compras", "itens", "resultados")
    }


def auditar_ausencias(bases):
    """Conta por coluna; zero numérico não entra como ausência."""
    registros = []
    for nome, tabela in bases.items():
        for coluna in tabela.columns:
            valores = tabela[coluna]
            nulos = valores.map(lambda v: limpeza.limpar_texto(v, False) is None)
            vazios = valores.map(limpeza.remover_invisiveis).map(limpeza.tirar_espacos).eq("")
            registros.append({
                "arquivo": nome, "coluna": coluna,
                "vazios": int((nulos & vazios).sum()),
                "marcadores": int((nulos & ~vazios).sum()),
                "ausencias": int(nulos.sum()),
            })
    return registros


def auditar_textos(bases):
    registros = []
    for nome, colunas in COLUNAS_TEXTO.items():
        for coluna in colunas:
            valores = bases[nome][coluna]
            registros.append({
                "campo": f"{nome}.{coluna}",
                "espacos": int(valores.map(limpeza.tirar_espacos).ne(valores).sum()),
                "invisiveis": int(valores.map(limpeza.remover_invisiveis).ne(valores).sum()),
                "acentuacao": int(valores.map(limpeza.consertar_acento).ne(valores).sum()),
            })
    return registros


def auditar_documentos(bases):
    """Verifica normalização, não os dígitos verificadores de CPF/CNPJ."""
    registros = []
    for nome, coluna in (("compras", "cnpj_orgao"), ("resultados", "ni_fornecedor")):
        tabela = bases[nome]
        tipos = ["PJ"] * len(tabela) if nome == "compras" else tabela["tipo_pessoa"]
        contagem = dict(ausentes=0, caracteres_nao_numericos=0,
                        zeros_repostos=0, estrangeiros=0, invalidos=0)
        for original, tipo in zip(tabela[coluna], tipos):
            texto = limpeza.limpar_texto(original)
            documento = limpeza.limpar_documento(original, tipo)
            if texto is None:
                contagem["ausentes"] += 1
            elif tipo == "PE":
                contagem["estrangeiros"] += 1
            else:
                digitos = "".join(c for c in texto if c.isdigit())
                tamanho = 14 if tipo == "PJ" else 11 if tipo == "PF" else (14 if len(digitos) > 11 else 11)
                contagem["caracteres_nao_numericos"] += int(digitos != texto)
                contagem["zeros_repostos"] += int(documento is not None and len(digitos) < tamanho)
                contagem["invalidos"] += int(documento is None)
        registros.append({"campo": f"{nome}.{coluna}", **contagem})
    return registros


def auditar_numeros(bases):
    registros = []
    for nome, colunas in COLUNAS_NUMERO.items():
        for coluna in colunas:
            valores = bases[nome][coluna]
            numeros = valores.map(limpeza.converter_numero)
            ausentes = valores.map(lambda v: limpeza.limpar_texto(v, False) is None)
            registros.append({
                "campo": f"{nome}.{coluna}",
                "com_R$": int(valores.str.contains("R$", regex=False).sum()),
                "com_virgula": int(valores.str.contains(",", regex=False).sum()),
                "zeros": int(numeros.eq(0).sum()),
                "negativos": int(numeros.lt(0).sum()),
                "ausentes": int(ausentes.sum()),
                "nao_convertiveis": int((numeros.isna() & ~ausentes).sum()),
            })
    return registros


def auditar_datas(bases):
    resumos, formatos = [], {f: {"formato": f} for f in limpeza.FORMATOS_DATA}
    for nome, coluna in COLUNAS_DATA.items():
        valores = bases[nome][coluna]
        datas = valores.map(limpeza.converter_data)
        ausentes = valores.map(lambda v: limpeza.limpar_texto(v) is None)
        resumos.append({
            "campo": f"{nome}.{coluna}", "ausentes": int(ausentes.sum()),
            "nao_convertiveis": int((datas.isna() & ~ausentes).sum()),
        })
        for registro in formatos.values():
            registro[nome] = 0
        for valor, data in zip(valores, datas):
            if data is None or pd.isna(data):
                continue
            texto = limpeza.limpar_texto(valor)[:10]
            for formato in limpeza.FORMATOS_DATA:
                try:
                    datetime.strptime(texto, formato)
                except ValueError:
                    continue
                formatos[formato][nome] += 1
                break
    return resumos, list(formatos.values())


def auditar_chaves(bases):
    chaves = {"compras": ["numero_controle_pncp"], "itens": CHAVE_ITEM,
              "resultados": CHAVE_ITEM + ["sequencial_resultado"]}
    registros = []
    for nome, colunas in chaves.items():
        tabela = bases[nome]
        registros.append({
            "arquivo": nome, "chave_bruta": " + ".join(colunas),
            "linhas_com_chave_repetida": int(tabela.duplicated(colunas, keep=False).sum()),
        })
    return registros


def auditar_regras(bases):
    """Reproduz a seleção em cópias; nenhuma tabela é gravada."""
    compras = bases["compras"][["numero_controle_pncp", "data_publicacao", "modalidade_id"]].copy()
    itens = bases["itens"][[*CHAVE_ITEM, "quantidade", "valor_unitario_estimado", "sigiloso"]].copy()
    resultados = bases["resultados"].copy()
    for tabela in (itens, resultados):
        tabela["numero_item"] = tabela["numero_item"].astype(int)
    for tabela, colunas in ((itens, COLUNAS_NUMERO["itens"]),
                            (resultados, COLUNAS_NUMERO["resultados"])):
        for coluna in colunas:
            tabela[coluna] = tabela[coluna].map(limpeza.converter_numero)

    cancelados = resultados["data_cancelamento"].str.strip().ne("")
    resultados = resultados[~cancelados].copy()
    resultados["ordem"] = pd.to_numeric(resultados["ordem_classificacao_srp"], errors="coerce").fillna(1)
    resultados["sequencial"] = pd.to_numeric(resultados["sequencial_resultado"], errors="coerce").fillna(1)
    vencedores = resultados.sort_values([*CHAVE_ITEM, "ordem", "sequencial"]).drop_duplicates(CHAVE_ITEM)
    vencedores = vencedores[[*CHAVE_ITEM, *COLUNAS_NUMERO["resultados"], "data_resultado"]]

    # As validações impedem que chaves duplicadas multipliquem os itens na auditoria.
    candidatos = itens.merge(vencedores, on=CHAVE_ITEM, how="left", indicator=True, validate="one_to_one")
    sem_resultado = candidatos["_merge"].eq("left_only")
    fato = candidatos[~sem_resultado].drop(columns="_merge").merge(
        compras, on="numero_controle_pncp", how="left", indicator=True, validate="many_to_one",
    )
    sem_compra = fato["_merge"].eq("left_only")
    fato = fato[~sem_compra].copy()
    quantidade = fato["quantidade_homologada"].where(fato["quantidade_homologada"] > 0, fato["quantidade"])
    estimado = (quantidade * fato["valor_unitario_estimado"]).round(2)
    homologado = (quantidade * fato["valor_unitario_homologado"]).round(2)
    motivos = {
        "Quantidade ausente ou nao positiva": ~(quantidade > 0),
        "Unitario estimado ausente ou nao positivo": ~(fato["valor_unitario_estimado"] > 0),
        "Unitario homologado ausente ou nao positivo": ~(fato["valor_unitario_homologado"] > 0),
        "Orcamento sigiloso": fato["sigiloso"].str.lower().eq("true"),
        "Estimado inferior a R$ 1": estimado < 1,
        "Homologado superior a 1000 vezes o estimado": homologado > 1000 * estimado,
        "Algum total superior a R$ 1 trilhao": (estimado > 1e12) | (homologado > 1e12),
    }
    rejeitados = pd.DataFrame(motivos).any(axis=1)
    validos = ~rejeitados
    publicacao = fato["data_publicacao"].map(limpeza.converter_data)
    homologacao = fato["data_resultado"].map(limpeza.converter_data)
    cronologia_invalida = validos & (homologacao < publicacao)
    comparaveis = validos & pd.to_numeric(fato["modalidade_id"], errors="raise").ne(12) & (homologado / estimado).between(0.1, 10)
    resumo = {
        "Resultados cancelados": int(cancelados.sum()),
        "Itens sem resultado elegivel": int(sem_resultado.sum()),
        "Itens com vencedor mas sem compra correspondente": int(sem_compra.sum()),
        "Itens antes da rejeicao": len(fato),
        "Itens distintos rejeitados (uniao dos motivos)": int(rejeitados.sum()),
        "Itens validos": int(validos.sum()),
        "Itens comparaveis": int(comparaveis.sum()),
        "Homologacoes anteriores a publicacao nos itens validos": int(cronologia_invalida.sum()),
    }
    contagens = [{"motivo": motivo, "ocorrencias": int(mascara.sum())}
                 for motivo, mascara in motivos.items()]
    return resumo, contagens


def auditar_processados():
    """Confere as tabelas já geradas, quando os cinco arquivos estão presentes."""
    dimensoes = {
        "dim_orgao": ("sk_orgao", "cnpj_orgao"),
        "dim_fornecedor": ("sk_fornecedor", "ni_fornecedor"),
        "dim_modalidade": ("sk_modalidade", "modalidade_id"),
        "dim_localidade": ("sk_localidade", "uf_sigla"),
    }
    nomes = ["fato_item_contratado", *dimensoes]
    if not all((config.PASTA_PROCESSED / f"{n}.csv").is_file() for n in nomes):
        return []
    tabelas = {n: pd.read_csv(config.PASTA_PROCESSED / f"{n}.csv", dtype=str,
                             keep_default_na=False, encoding="utf-8-sig") for n in nomes}
    fato = tabelas["fato_item_contratado"]
    registros = [{"tabela": "fato_item_contratado", "linhas": len(fato),
                  "linhas_com_chave_repetida": int(fato.duplicated(CHAVE_ITEM, keep=False).sum()),
                  "linhas_com_chave_natural_repetida": "-", "referencias_sem_correspondencia": "-"}]
    for nome, (sk, natural) in dimensoes.items():
        dim = tabelas[nome]
        registros.append({
            "tabela": nome, "linhas": len(dim),
            "linhas_com_chave_repetida": int(dim.duplicated(sk, keep=False).sum()),
            "linhas_com_chave_natural_repetida": int(dim.duplicated(natural, keep=False).sum()),
            "referencias_sem_correspondencia": int((~fato[sk].isin(dim[sk])).sum()),
        })
    return registros


def gerar_relatorio(bases):
    linhas = ["AUDITORIA DE DADOS - PNCP", "Somente leitura dos CSVs; sem acesso ao MySQL."]

    def tabela(titulo, registros):
        linhas.extend(["", "=" * 100, titulo, "=" * 100])
        linhas.append(pd.DataFrame(registros).to_string(index=False) if registros else "Sem ocorrencias.")

    tabela("1. REGISTROS POR ARQUIVO", [{"arquivo": n, "linhas": len(t), "colunas": len(t.columns)}
                                             for n, t in bases.items()])
    ausencias = auditar_ausencias(bases)
    tabela("2. AUSENCIAS POR COLUNA (zero numerico preservado)",
           [r for r in ausencias if r["ausencias"]])
    tabela("TOTAIS DE AUSENCIAS POR ARQUIVO", [
        {"arquivo": nome, **{c: sum(r[c] for r in ausencias if r["arquivo"] == nome)
                             for c in ("vazios", "marcadores", "ausencias")}}
        for nome in bases
    ])
    linhas.append("Ausencia nao significa necessariamente erro; cancelamento vazio pode ser esperado.")
    tabela("3. TEXTOS (efeitos isolados; ocorrencias podem se sobrepor)", auditar_textos(bases))
    tabela("4. DOCUMENTOS", auditar_documentos(bases))
    linhas.append("Caracteres e zeros: documentos nacionais. Invalidos excluem ausentes; nao se validam digitos verificadores.")
    tabela("5. NUMEROS UTILIZADOS NO PIPELINE", auditar_numeros(bases))
    datas, formatos = auditar_datas(bases)
    tabela("6. DATAS UTILIZADAS NOS INDICADORES", datas)
    tabela("FORMATOS RECONHECIDOS (apos descarte do horario)", formatos)
    tabela("7. CHAVES BRUTAS (contagem de todas as linhas em grupos repetidos)", auditar_chaves(bases))
    resumo, motivos = auditar_regras(bases)
    tabela("8. SELECAO, REJEICAO E CRONOLOGIA - SIMULACAO EM MEMORIA", [
        {"indicador": nome, "quantidade": quantidade} for nome, quantidade in resumo.items()
    ])
    tabela("MOTIVOS DE REJEICAO", motivos)
    linhas.append("Os motivos se sobrepoem: nao somar ocorrencias para obter itens rejeitados.")
    linhas.append("Homologacao anterior a publicacao anula a data e o ciclo; o item valido permanece na fato.")
    processados = auditar_processados()
    if processados:
        tabela("9. ARQUIVOS PROCESSADOS EXISTENTES (nao sao regenerados por esta auditoria)", processados)
    else:
        linhas.extend(["", "Conferencia dos processados nao executada: gere as cinco tabelas com src.montar_tabelas."])
    return "\n".join(linhas) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--saida", type=Path, help="Arquivo de texto opcional; exemplo: data/auditoria.log")
    argumentos = parser.parse_args(argv)
    try:
        # Protege os CSVs e o código contra um caminho de saída escolhido por engano.
        if argumentos.saida and argumentos.saida.suffix.lower() not in {".log", ".txt", ".md"}:
            raise ValueError("A saida deve ser um arquivo .log, .txt ou .md, nunca um CSV ou codigo Python.")
        if argumentos.saida and argumentos.saida.resolve().is_relative_to(config.PASTA_RAIZ / "src"):
            raise ValueError("Salve o relatorio fora de src; por exemplo, data/auditoria.log.")
        relatorio = gerar_relatorio(ler_bases())
        if argumentos.saida:
            argumentos.saida.parent.mkdir(parents=True, exist_ok=True)
            argumentos.saida.write_text(relatorio, encoding="utf-8")
        print(relatorio, end="")
        if argumentos.saida:
            print(f"\nRelatorio salvo em: {argumentos.saida}")
    except (OSError, KeyError, ValueError) as erro:
        print(f"Nao foi possivel concluir a auditoria: {erro}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
