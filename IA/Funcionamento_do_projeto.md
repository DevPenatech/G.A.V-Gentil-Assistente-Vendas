# **REGRAS**

1. **Abordagem IA-First**:  
    Todas as interações devem passar pela IA antes de qualquer resposta humana. A IA deve:
    
    - Extrair **intenção do cliente**.
        
    - Classificar a mensagem em **tipos de intenção** (ex.: buscar produto, editar carrinho, fechar pedido, dúvidas gerais).
        
    - Pedir esclarecimentos se a intenção não estiver clara.
        
2. **Contexto/Historicidade**:  
    Cada resposta da IA deve considerar o **histórico das últimas interações** (últimas mensagens da conversa + estado do carrinho).
    
3. **Formatação otimizada**:  
    As mensagens enviadas ao cliente devem ser curtas, claras e visualmente fáceis de entender no WhatsApp (listas numeradas, emojis apenas se úteis, separadores para carrinho e produtos).
    
4. **Gestão de contexto dinâmico**:  
    Se o cliente mudar de assunto no meio de uma ação (ex.: estava escolhendo produto, mas pediu outra coisa), a IA deve **interromper a ação anterior e seguir o novo fluxo**, sem quebrar a experiência.
    
5. **Logs detalhados**:  
    O sistema deve registrar cada etapa da IA com informações completas para auditoria, incluindo:
    
    - Timestamp da ação.
        
    - Identificador único de sessão.
        
    - Identificador do usuário (quando aplicável).
        
    - Intenção detectada.
        
    - Ação tomada.
        
    - Estado do carrinho antes/depois.
        
    - Mensagem enviada ao cliente.
        
6. **Idioma padrão**:  
    Todo o sistema (funções, variáveis, docstrings, logs e respostas) deve estar em **português do Brasil**.
    
7. **Fallback / Respostas neutras**:  
    Caso a IA não consiga entender a intenção ou não tenha dados suficientes (ex.: produto inexistente), deve responder educadamente pedindo mais detalhes, e nunca retornar mensagens em branco.
    

---

# **FUNÇÕES ESPERADAS**

## 1. Buscar produtos

- **Por nome e/ou marca**:  
    IA deve extrair **nome do produto** e **marca** quando disponíveis.
    
    - Se tiver só nome → busca por nome.
        
    - Se tiver só marca → busca por marca.
        
    - Se tiver ambos → busca combinada.
        
- **Por categoria**:  
    IA deve identificar categorias amplas (Ex.: cerveja, balas, detergente, tempero).
    
- **Por promoção**:  
    IA deve retornar até **10 produtos em promoção**.
    

**Formato de resposta da IA (exemplo):**

```
🔎 Encontrei os seguintes produtos:

1. Cerveja Brahma Lata 350ml – R$ 3,99
2. Cerveja Skol Lata 350ml – R$ 3,89
3. Cerveja Heineken Long Neck 330ml – R$ 5,99

🎯 Promoções semelhantes:
- Skol Pack 12un: de R$ 46,80 por R$ 39,90 (-15%)
- Brahma Duplo Malte 1L: de R$ 12,90 por R$ 9,90 (-23%)
```

## 2. Editar carrinho

Funções suportadas:

- **Adicionar**: "Quero adicionar 6 cervejas"
    
- **Remover**: "Tira 5 cervejas"
    
- **Atualizar quantidade**: "Muda pra 7 cervejas"
    
- **Limpar carrinho**: "Esvazia o carrinho"
    

Após cada ação, a IA deve mostrar o **estado atualizado do carrinho**, por exemplo:

```
🛒 Seu carrinho atual:
- 6x Cerveja Skol Lata 350ml – R$ 3,89 cada
- 2x Sabonete Dove – R$ 4,50 cada
Total: R$ 34,18
```

## 3. Fechar pedido

- IA deve solicitar **CNPJ do cliente** antes de concluir.
    
- Após receber o CNPJ válido:
    
    - Gerar o pedido.
        
    - Mostrar resumo para confirmação.
        

Exemplo:

```
✅ Pedido gerado com sucesso!

🛒 Itens:
- 6x Cerveja Skol Lata 350ml – R$ 3,89
- 2x Sabonete Dove – R$ 4,50
Total: R$ 34,18

📌 CNPJ informado: 12.345.678/0001-90
```

---

# **FUNÇÕES ADICIONAIS **

- **Consultar carrinho**: Cliente pode perguntar "o que tenho no carrinho?" e a IA retorna o estado atual.
    
- **Cancelar pedido**: Antes da finalização, cliente pode desistir e IA limpa carrinho.
    
- **Atalhos de ajuda**: Cliente pode enviar "ajuda" ou "menu" e a IA responde com um resumo dos comandos disponíveis.
    
- **Validação de CNPJ**: Simples regex/verificação básica antes de aceitar o dado.
    

---