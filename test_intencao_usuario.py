from unittest.mock import patch

from IA.core.gerenciador_sessao import detectar_tipo_intencao_usuario


def test_quero_finalizar_classificado_como_checkout():
    dados_sessao = {"historico_conversa": [{"role": "user", "content": "oi"}]}
    with patch("IA.core.gerenciador_sessao.detectar_intencao_usuario_com_ia") as mock_ai:
        mock_ai.return_value = {"nome_ferramenta": "checkout", "parametros": {}}
        resultado = detectar_tipo_intencao_usuario("quero finalizar", dados_sessao)
        assert resultado == "CHECKOUT"
        args, _ = mock_ai.call_args
        assert args[0] == "quero finalizar"
        assert "user: oi" in args[1]


def test_intencao_desconhecida_retorna_general():
    dados_sessao = {"historico_conversa": []}
    with patch("IA.core.gerenciador_sessao.detectar_intencao_usuario_com_ia") as mock_ai:
        mock_ai.return_value = {"nome_ferramenta": "algo_inesperado", "parametros": {}}
        resultado = detectar_tipo_intencao_usuario("mensagem aleatoria", dados_sessao)
        assert resultado == "GENERAL"
