/* ============================================================================
    PNCP | Análise das contratações públicas
    ===========================================================================
*/  

USE pncp_controladoria;

/* ============================================================================
   01 | ECONOMIA GLOBAL
   ============================================================================
   Pergunta: Qual é o percentual e o valor financeiro nominal economizado pelo 
   governo (diferença entre valor estimado e valor homologado)?
   
   Volume homologado total: R$ 8.044.498.805,74
   Valor estimado da base comparável: R$ 6.867.663.469,91
   Valor financeiro economizado: R$ 992.861.686,95
   Percentual de economia: 14,46% 
*/
SELECT
    COUNT(*)                                                            AS total_itens,
    SUM(valor_total_homologado)                                         AS volume_homologado,
    SUM(CASE WHEN comparavel = 1 THEN 1 ELSE 0 END)                     AS itens_comparaveis,
    SUM(CASE WHEN comparavel = 1 THEN valor_total_estimado ELSE 0 END)  AS estimado_comparavel,
    SUM(CASE WHEN comparavel = 1 THEN economia_valor ELSE 0 END)        AS economia_nominal,
    ROUND(100.0 * SUM(CASE WHEN comparavel = 1 
                      THEN economia_valor ELSE 0 END) / NULLIF(SUM(CASE WHEN comparavel = 1 
                      THEN valor_total_estimado ELSE 0 END), 0), 2)     AS economia_percentual
FROM fato_item_contratado;

/* ============================================================================
   02 | CONCENTRAÇÃO EM FORNECEDORES
   ============================================================================
   Pergunta: Quem são os maiores fornecedores em volume financeiro e qual 
   percentual do orçamento público está concentrado neles?
   
   Volume financimento dos 10 maiores fornecedores
   Fornecedor	                    Volume Homologado
   NOW SEGUROS SA	                R$ 1.060.000.000,00
   CONSTRUTORA CIDADE LIMITADA	    R$   524.935.394,97
   BANCO BRADESCO S.A.	            R$   379.194.320,07
   CONSTRUTORA NORTE BRASIL LTDA.	R$   335.401.470,80
   LCM CONSTRUCAO E COMERCIO S.A	R$   228.885.493,53
   CONSTRUTORA OTIMA LTDA	        R$   192.344.816,46
   CONPATE ENGENHARIA LTDA	        R$   166.644.303,41
   INDIGO HIVE CONSULT. EM TI S.A.	R$   160.000.000,00
   CONSTRUTORA HIDROS LTDA	        R$   159.193.730,62
   ARTELESTE CONSTRUCOES LIMITADA	R$   125.884.500,00

   Participação no volume homologado dos 10 maiores fornecedores
   Fornecedor	                         %
   NOW SEGUROS SA	                13,18%
   CONSTRUTORA CIDADE LIMITADA	     6,53%
   BANCO BRADESCO S.A.	             4,71%
   CONSTRUTORA NORTE BRASIL LTDA.	 4,17%
   LCM CONSTRUCAO E COMERCIO S.A	 2,85%
   CONSTRUTORA OTIMA LTDA	         2,39%
   CONPATE ENGENHARIA LTDA	         2,07%
   INDIGO HIVE CONSULT. EM TI S.A.	 1,99%
   CONSTRUTORA HIDROS LTDA	         1,98%
   ARTELESTE CONSTRUCOES LIMITADA	 1,56%

*/
SELECT
    d.ni_fornecedor,
    d.nome_fornecedor,
    COUNT(*)                                AS itens_contratados,
    SUM(f.valor_total_homologado)           AS volume_homologado,
    ROUND(
        100.0 * SUM(f.valor_total_homologado)
        / NULLIF((SELECT SUM(valor_total_homologado) 
        FROM fato_item_contratado), 0), 4) AS participacao_no_volume_percentual
FROM fato_item_contratado                  AS f
JOIN dim_fornecedor                        AS d ON d.sk_fornecedor = f.sk_fornecedor
GROUP BY d.ni_fornecedor, d.nome_fornecedor
ORDER BY volume_homologado DESC, d.ni_fornecedor
LIMIT 10;

/* ============================================================================
   03 | EFICÁCIA DAS MODALIDADES
   ============================================================================
   Quais modalidades licitatórias trazem maior deságio/economia e quais 
   concentram o maior volume de recursos?
   
   Modalidade                   Economia Nominal	Economia Percentual
   Pregão - Eletrônico	       R$ 158.700.450,06	             24,02%
   Concorrência - Eletrônica   R$ 782.073.491,19	             14,27%
   Inexigibilidade	           R$  17.831.855,99	              8,77%
   Concorrência - Presencial   R$  32.381.222,93	              6,79%
   Dispensa	                   R$   1.874.083,49	              4,49%
   Pregão - Presencial	       R$         583,29	              0,02%
   Credenciamento	           R$           0,00	     Não aplicável (NULL)

   Credenciamento não possui itens comparáveis; sua economia percentual é NULL.

*/
SELECT
    d.modalidade_id,
    d.nome_modalidade,
    COUNT(*)                                          AS total_itens,
    SUM(f.valor_total_homologado)                     AS volume_homologado,
    SUM(CASE WHEN f.comparavel = 1 THEN 1 ELSE 0 END) AS itens_comparaveis,
    SUM(CASE WHEN f.comparavel = 1 THEN f.economia_valor ELSE 0 END)
        AS economia_nominal,
    ROUND(
        100.0 * SUM(CASE WHEN f.comparavel = 1 THEN f.economia_valor ELSE 0 END)
        / NULLIF(SUM(CASE WHEN f.comparavel = 1 THEN f.valor_total_estimado ELSE 0 END), 0), 2
    ) AS economia_percentual
FROM fato_item_contratado                             AS f
JOIN dim_modalidade                                   AS d ON d.sk_modalidade = f.sk_modalidade
GROUP BY d.modalidade_id, d.nome_modalidade
ORDER BY economia_percentual DESC, volume_homologado DESC, d.modalidade_id;

/* ============================================================================
   04 | TEMPO DO CICLO DE COMPRAS
   ============================================================================
   Pergunta: Qual a duração média (em dias) entre o lançamento do edital e a sua 
   homologação final, segmentada por órgão?

   As médias dos órgãos com pelo menos cinco ciclos válidos variam de 0 a 266,3 dias.
   O maior ciclo individual da base é de 611 dias.
*/
SELECT
    d.nome_orgao,
    COUNT(DISTINCT d.cnpj_orgao) AS unidades_compradoras,
    COUNT(*)                     AS total_itens,
    COUNT(f.dias_ciclo)          AS itens_com_ciclo,
    ROUND(AVG(f.dias_ciclo), 1)  AS ciclo_medio_dias,
    MAX(f.dias_ciclo)            AS ciclo_maximo_dias
FROM fato_item_contratado        AS f
JOIN dim_orgao                   AS d ON d.sk_orgao = f.sk_orgao
GROUP BY d.nome_orgao
HAVING COUNT(f.dias_ciclo) >= 5
ORDER BY ciclo_medio_dias DESC, d.nome_orgao;

/* ============================================================================
   05 | DISTRIBUIÇÃO TERRITORIAL
   ============================================================================
   Pergunta: Quais estados e regiões concentram as maiores despesas e quais apresentam os melhores indicadores de desconto?
   
   Três primeiros estados com maiores despesas:
   UF    Volume Homologado
   DF    R$ 3.135.638.456,35
   RS    R$   820.584.056,64
   RJ    R$   461.925.602,27

   Regiões com melhores indicadores de desconto (economia percentual):
   Região         Economia Percentual
   Norte                    21,43%
   Centro-Oeste	            17,02%
   Nordeste                 14,18%
   Sudeste                  11,62%
   Sul                       7,96%
    
*/

-- Visão por estado: participação no total global e economia local.
SELECT
    d.uf_sigla,
    d.uf_nome,
    d.regiao,
    SUM(f.valor_total_homologado) AS volume_homologado,
    ROUND(100.0 * SUM(f.valor_total_homologado)
        / NULLIF((SELECT SUM(valor_total_homologado) 
        FROM fato_item_contratado), 0), 2
    )   AS participacao_no_volume_percentual,
    SUM(CASE WHEN f.comparavel = 1 THEN f.economia_valor ELSE 0 END)
        AS economia_nominal,
    ROUND(100.0 * SUM(CASE WHEN f.comparavel = 1 THEN f.economia_valor ELSE 0 END)
        / NULLIF(SUM(CASE WHEN f.comparavel = 1 THEN f.valor_total_estimado ELSE 0 END), 0), 2
    ) AS economia_percentual
FROM fato_item_contratado AS f
JOIN dim_localidade       AS d ON d.sk_localidade = f.sk_localidade
GROUP BY d.uf_sigla, d.uf_nome, d.regiao
ORDER BY volume_homologado DESC, d.uf_sigla;

-- Visão por região: taxas recalculadas pelas somas, sem média entre UFs.
SELECT
    d.regiao,
    SUM(f.valor_total_homologado) AS volume_homologado,
    ROUND(100.0 * SUM(f.valor_total_homologado)
        / NULLIF((SELECT SUM(valor_total_homologado) FROM fato_item_contratado), 0), 2
    ) AS participacao_no_volume_percentual,
    SUM(CASE WHEN f.comparavel = 1 THEN f.economia_valor ELSE 0 END)
        AS economia_nominal,
    ROUND(100.0 * SUM(CASE WHEN f.comparavel = 1 THEN f.economia_valor ELSE 0 END)
        / NULLIF(SUM(CASE WHEN f.comparavel = 1 THEN f.valor_total_estimado ELSE 0 END), 0), 2
    ) AS economia_percentual
FROM fato_item_contratado AS f
JOIN dim_localidade       AS d ON d.sk_localidade = f.sk_localidade
GROUP BY d.regiao
ORDER BY volume_homologado DESC, d.regiao;

/* ============================================================================
   06 | PERFIL DOS GASTOS
   ============================================================================
   Pergunta: Como os recursos se distribuem entre bens, serviços e obras e engenharia?

   Obras e engenharia: R$ 4.892.362.732,70 (60,80%)
   Serviços:           R$ 2.940.950.885,18 (36,60%)
   Bens:               R$   211.185.187,86 ( 2,60%)
*/
SELECT
    perfil_gasto,
    COUNT(*)                    AS total_itens,
    SUM(valor_total_homologado) AS volume_homologado,
    ROUND(100.0 * SUM(valor_total_homologado)
        / NULLIF((SELECT SUM(valor_total_homologado) FROM fato_item_contratado), 0), 1
    ) AS participacao_no_volume_percentual
FROM fato_item_contratado
GROUP BY perfil_gasto
ORDER BY volume_homologado DESC, perfil_gasto;
