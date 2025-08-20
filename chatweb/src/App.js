// file: chatweb/src/App.js

import React, { useState, useEffect, useRef } from 'react';
import './App.css';

// Função para gerar um ID único para cada usuário
const generateUserId = () => {
  const timestamp = Date.now().toString(36);
  const randomStr = Math.random().toString(36).substring(2, 8);
  return `user_${timestamp}_${randomStr}`;
};

// Função para obter ou criar um ID de usuário único
const getUserId = () => {
  let userId = localStorage.getItem('webchat-user-id');
  if (!userId) {
    userId = generateUserId();
    localStorage.setItem('webchat-user-id', userId);
  }
  return userId;
};

// Função simples para renderizar markdown básico
const renderMarkdown = (text) => {
  // Converte markdown básico em HTML
  const html = text
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>') // **bold**
    .replace(/\*([^*]+)\*/g, '<em>$1</em>') // *italic*
    .replace(/^#{3}\s(.+)$/gm, '<h3>$1</h3>') // ### heading
    .replace(/^#{2}\s(.+)$/gm, '<h2>$1</h2>') // ## heading
    .replace(/^#{1}\s(.+)$/gm, '<h1>$1</h1>') // # heading
    .replace(/^\*\s(.+)$/gm, '<li>$1</li>') // * list item
    .replace(/(\n<li>.*<\/li>\n)/gs, '<ul>$1</ul>') // wrap list items
    .replace(/`([^`]+)`/g, '<code>$1</code>') // `code`
    .replace(/\n/g, '<br>'); // quebras de linha

  return { __html: html };
};

function App() {
  // 1. Estado para controlar o tema atual. Lê do localStorage para lembrar a escolha do usuário.
  const [theme, setTheme] = useState(localStorage.getItem('chat-theme') || 'light');

  const [messages, setMessages] = useState([
    { from: 'bot', text: '🎉 **Olá! Seja bem-vindo à Comercial Esperança!**\n\nEu sou o **G.A.V.** (Gentil Assistente de Vendas) e estou aqui para te ajudar com seus pedidos de forma rápida e personalizada! 😊\n\nPara começarmos, preciso apenas do CNPJ da sua empresa:\n📄 Digite seu CNPJ (pode ser com ou sem pontuação)' }
  ]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const messagesEndRef = useRef(null);

  // 2. useEffect para aplicar a classe 'dark' no body e salvar a escolha
  useEffect(() => {
    // Adiciona ou remove a classe 'dark' do elemento <body>
    document.body.classList.toggle('dark', theme === 'dark');
    // Salva a preferência de tema no localStorage do navegador
    localStorage.setItem('chat-theme', theme);
  }, [theme]); // Roda sempre que o estado 'theme' mudar

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(scrollToBottom, [messages]);

  const handleSend = async (e) => {
    e.preventDefault();
    if (!input.trim()) return;

    const userMessage = { from: 'user', text: input };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsTyping(true);

    try {
      const response = await fetch('/webchat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: input,
          sender_id: getUserId()
        }),
      });

      const data = await response.json();
      const botMessage = { from: 'bot', text: data.reply };
      setMessages(prev => [...prev, botMessage]);

    } catch (error) {
      console.error("Erro ao enviar mensagem:", error);
      const errorMessage = { from: 'bot', text: 'Desculpe, não consegui me conectar ao backend.' };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsTyping(false);
    }
  };

  // 3. Função para alternar o tema
  const toggleTheme = () => {
    setTheme(prevTheme => (prevTheme === 'light' ? 'dark' : 'light'));
  };

  // 4. Função para iniciar nova sessão (novo usuário)
  const startNewSession = () => {
    // Remove o ID do usuário atual
    localStorage.removeItem('webchat-user-id');
    // Limpa as mensagens
    setMessages([
      { from: 'bot', text: '🔄 **Nova sessão iniciada**\n\n🎉 **Olá! Seja bem-vindo à Comercial Esperança!**\n\nEu sou o **G.A.V.** (Gentil Assistente de Vendas) e estou aqui para te ajudar com seus pedidos de forma rápida e personalizada! 😊\n\nPara começarmos, preciso apenas do CNPJ da sua empresa:\n📄 Digite seu CNPJ (pode ser com ou sem pontuação)' }
    ]);
    // Gera novo ID para próxima mensagem
    getUserId(); // Isso criará um novo ID
  };

  return (
    <div className="chat-container">
      {/* 5. Cabeçalho com botões de controle */}
      <div className="chat-header">
        <h3>G.A.V. - Assistente de Vendas</h3>
        <div className="header-buttons">
          <button onClick={startNewSession} className="new-session-btn" title="Iniciar nova sessão">
            🔄 Nova Sessão
          </button>
          <button onClick={toggleTheme} className="theme-toggle" title="Alternar tema">
            {theme === 'light' ? '🌙' : '☀️'}
          </button>
        </div>
      </div>

      <div className="chat-window">
        {messages.map((msg, index) => (
          <div key={index} className={`message ${msg.from}`}>
            {msg.from === 'bot' ? (
              // Para mensagens do bot, usar renderização markdown
              <div className="markdown-content" dangerouslySetInnerHTML={renderMarkdown(msg.text)} />
            ) : (
              // Para mensagens do usuário, manter texto simples
              <p>{msg.text}</p>
            )}
          </div>
        ))}
        {isTyping && (
          <div className="message bot typing">
            <p><span>.</span><span>.</span><span>.</span></p>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>
      <form onSubmit={handleSend} className="chat-input-form">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Digite sua mensagem..."
          autoFocus
        />
        <button type="submit">Enviar</button>
      </form>
    </div>
  );
}

export default App;