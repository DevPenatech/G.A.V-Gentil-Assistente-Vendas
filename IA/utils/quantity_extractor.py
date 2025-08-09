# file: IA/utils/quantity_extractor.py
import re
from typing import Union, Optional

class QuantityExtractor:
    """Extrai quantidades de texto em linguagem natural portuguesa."""
    
    def __init__(self):
        # Mapeamento de números por extenso
        self.numbers_map = {
            # Números básicos
            'zero': 0, 'um': 1, 'uma': 1, 'dois': 2, 'duas': 2, 'três': 3, 'tres': 3,
            'quatro': 4, 'cinco': 5, 'seis': 6, 'sete': 7, 'oito': 8, 'nove': 9,
            'dez': 10, 'onze': 11, 'doze': 12, 'treze': 13, 'catorze': 14, 'quatorze': 14,
            'quinze': 15, 'dezesseis': 16, 'dezessete': 17, 'dezoito': 18, 'dezenove': 19,
            'vinte': 20, 'trinta': 30, 'quarenta': 40, 'cinquenta': 50,
            
            # Unidades especiais
            'meia': 0.5, 'meio': 0.5,
            'duzia': 12, 'dúzia': 12,
            'dezena': 10,
            'centena': 100,
            
            # Medidas comuns
            'pacote': 1, 'caixa': 1, 'unidade': 1, 'peça': 1, 'peca': 1,
            'garrafa': 1, 'lata': 1, 'pote': 1, 'saco': 1,
            'kg': 1, 'quilo': 1, 'kilo': 1,
            'litro': 1, 'l': 1,
            'gramas': 1, 'g': 1
        }
        
        # Multiplicadores
        self.multipliers = {
            'duzia': 12, 'dúzia': 12, 'duzia de': 12, 'dúzia de': 12,
            'meia duzia': 6, 'meia dúzia': 6,
            'dezena': 10, 'dezena de': 10
        }

    def extract_quantity(self, text: str) -> Optional[Union[int, float]]:
        """
        Extrai quantidade de um texto em português.
        
        Exemplos:
        - "5" → 5
        - "cinco" → 5
        - "duas" → 2
        - "meia duzia" → 6
        - "uma duzia" → 12
        - "2 pacotes" → 2
        - "meio quilo" → 0.5
        
        Returns:
            Quantidade extraída ou None se não encontrar
        """
        if not text or not text.strip():
            return None
            
        text = text.lower().strip()
        
        # 1. Tenta número direto primeiro (mais comum)
        number_match = re.search(r'\b(\d+(?:[.,]\d+)?)\b', text)
        if number_match:
            try:
                num_str = number_match.group(1).replace(',', '.')
                return float(num_str) if '.' in num_str else int(num_str)
            except ValueError:
                pass
        
        # 2. Verifica frases especiais com multiplicadores
        for phrase, multiplier in self.multipliers.items():
            if phrase in text:
                # Procura por número antes da frase
                pattern = rf'\b(\d+|{"|".join(self.numbers_map.keys())})\s*{re.escape(phrase)}'
                match = re.search(pattern, text)
                if match:
                    number_part = match.group(1)
                    base_num = self._convert_word_to_number(number_part)
                    if base_num is not None:
                        return base_num * multiplier
                else:
                    # Se não encontrou número, assume 1 (ex: "duzia" = "uma duzia")
                    return multiplier
        
        # 3. Busca números por extenso
        for word, number in self.numbers_map.items():
            if word in text:
                return number
        
        # 4. Padrões mais complexos
        patterns = [
            # "2 unidades", "5 pacotes"
            r'\b(\d+|' + '|'.join(self.numbers_map.keys()) + r')\s*(?:unidades?|pacotes?|caixas?|garrafas?|latas?)',
            # "meio kg", "1 litro"
            r'\b(meia?|meio|\d+|' + '|'.join(self.numbers_map.keys()) + r')\s*(?:kg|quilo|kilo|litros?|l)\b'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                number_part = match.group(1)
                return self._convert_word_to_number(number_part)
        
        return None
    
    def _convert_word_to_number(self, word: str) -> Optional[Union[int, float]]:
        """Converte palavra para número."""
        if not word:
            return None
            
        word = word.lower().strip()
        
        # Tenta número direto
        try:
            if '.' in word or ',' in word:
                return float(word.replace(',', '.'))
            else:
                return int(word)
        except ValueError:
            pass
        
        # Busca no mapeamento
        return self.numbers_map.get(word)

    def is_valid_quantity(self, quantity: Union[int, float]) -> bool:
        """Verifica se a quantidade é válida para compras."""
        if quantity is None:
            return False
        return 0 < quantity <= 1000  # Limites razoáveis

# Instância global para reuso
quantity_extractor = QuantityExtractor()

def extract_quantity(text: str) -> Optional[Union[int, float]]:
    """Função helper para extrair quantidade de texto."""
    return quantity_extractor.extract_quantity(text)

def is_valid_quantity(quantity: Union[int, float]) -> bool:
    """Função helper para validar quantidade."""
    return quantity_extractor.is_valid_quantity(quantity)

# Exemplos de uso e testes
if __name__ == "__main__":
    test_cases = [
        "5",
        "cinco",
        "duas",
        "meia duzia",
        "uma duzia",
        "2 pacotes",
        "meio quilo",
        "3 unidades",
        "duzia",
        "dez",
        "20",
        "1.5",
        "duas garrafas",
        "cinco latas",
        "uma caixa",
        "texto sem número",
        "",
        "100"
    ]
    
    extractor = QuantityExtractor()
    print("🧪 Testando Extrator de Quantidades:")
    print("=" * 50)
    
    for test in test_cases:
        result = extractor.extract_quantity(test)
        valid = extractor.is_valid_quantity(result) if result is not None else False
        status = "✅" if result is not None else "❌"
        print(f"{status} '{test}' → {result} {'(válido)' if valid else '(inválido)' if result is not None else ''}")