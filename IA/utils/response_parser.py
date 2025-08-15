import json
import re

def extract_json_from_ai_response(content: any):
    """
    Extrai JSON de resposta da IA mantendo flexibilidade para texto humano ou dicionários.
    """
    # Se o conteúdo já for um dicionário, retorne diretamente.
    if isinstance(content, dict):
        return content

    # Garante que o conteúdo seja uma string para as operações seguintes.
    if not isinstance(content, str):
        content = str(content)

    # 1. Tenta JSON direto (ideal)
    try:
        return json.loads(content.strip())
    except:
        pass
    
    # 2. Procura JSON em meio a texto (IA pode explicar + dar JSON)
    json_patterns = [
        r'\{[^{}]*"tool_name"[^{}]*\}',  # JSON simples
        r'\{(?:[^{}]|{[^{}]*})*\}',     # JSON aninhado
        r'```json\s*(\{.*?\})\s*```',   # JSON em markdown
        r'(?:resposta|json|formato):\s*(\{.*?\})', # JSON após prefixos
    ]
    
    for pattern in json_patterns:
        matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)
        for match in matches:
            try:
                return json.loads(match)
            except:
                continue
    
    # 3. Se não encontrou JSON, assume que IA quer conversar
    return {
        "tool_name": "handle_chitchat",
        "parameters": {
            "response_text": content.strip()
        }
    }

def validate_json_structure(parsed_json: dict, available_tools: list) -> bool:
    """Valida se o JSON tem estrutura mínima necessária"""
    
    if not isinstance(parsed_json, dict):
        return False
        
    if "tool_name" not in parsed_json:
        return False
        
    if "parameters" not in parsed_json:
        return False
        
    tool_name = parsed_json["tool_name"]
    if tool_name not in available_tools:
        return False
        
    # Validações específicas por ferramenta
    params = parsed_json["parameters"]
    
    if tool_name == "handle_chitchat" and "response_text" not in params:
        return False
        
    if tool_name == "smart_cart_update":
        required = ["product_name", "action", "quantity"]
        if not all(key in params for key in required):
            return False
            
    return True
