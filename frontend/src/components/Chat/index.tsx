import React, { useState, useRef, useEffect } from 'react';
import {
  Box,
  Container,
  Stack,
  useTheme,
} from '@mui/material';
import { MessageBubble } from './MessageBubble';
import { ChatInput } from './ChatInput';
import { SuggestedQuestions } from './SuggestedQuestions';
import { ChatHeader } from './ChatHeader';
import toast from 'react-hot-toast';
import { config } from '../../config';
import DocumentViewer from '../DocumentViewer';
import VideoViewer from '../VideoViewer';

interface Source {
  title: string;
  filename: string;
  content: string;
  summary?: string;
  concepts?: string;
  score: number;
  document_id?: string;
  type?: string;
  file_type?: string;
  fileUrl?: string;
  chunk_id?: string;
  page_number?: number;
  section?: string;
  start_time?: number;
  end_time?: number;
  duration?: number;
  timestamp_display?: string;
  content_type?: string;
}

interface Message {
  id: string;
  content: string;
  role: 'user' | 'assistant';
  timestamp: Date;
  isStreaming?: boolean;
  sources?: Source[];
}

export const Chat: React.FC = () => {
  const theme = useTheme();
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedDocument, setSelectedDocument] = useState<Source | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSendMessage = async (message: string) => {
    if (!message.trim() || isLoading) return;

    const userMessage: Message = {
      id: `msg-${Date.now()}-user`,
      content: message,
      role: 'user',
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setIsLoading(true);

    const assistantMessageId = `msg-${Date.now()}-assistant`;
    const streamingMessage: Message = {
      id: assistantMessageId,
      content: '',
      role: 'assistant',
      timestamp: new Date(),
      isStreaming: true,
    };

    setMessages(prev => [...prev, streamingMessage]);

    try {
      console.log('Making streaming API request to:', `${config.API_BASE_URL}/api/chat/query/stream`);

      const response = await fetch(`${config.API_BASE_URL}/api/chat/query/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query: message,
          session_id: `session-${Date.now()}`,
        }),
      });

      console.log('Response status:', response.status, response.statusText);

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        throw new Error('No response body reader available');
      }

      let accumulatedContent = '';
      let sources: Source[] = [];
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          console.log('Stream reading complete');
          break;
        }

        const chunk = decoder.decode(value, { stream: true });
        console.log('Received chunk:', chunk);
        buffer += chunk;
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              console.log('Parsed SSE data:', data);

              if (data.type === 'sources') {
                sources = data.sources || [];
                console.log('Received initial sources:', sources.length);
              } else if (data.type === 'sources_update') {
                sources = data.sources || [];
                console.log('Updated sources:', sources.length);
                setMessages(prev => prev.map(msg =>
                  msg.id === assistantMessageId
                    ? { ...msg, sources }
                    : msg
                ));
              } else if (data.type === 'content') {
                accumulatedContent += data.content;
                setMessages(prev => prev.map(msg =>
                  msg.id === assistantMessageId
                    ? {
                        ...msg,
                        content: accumulatedContent,
                        isStreaming: true,
                        sources: sources,
                      }
                    : msg
                ));
              } else if (data.type === 'done') {
                setMessages(prev => prev.map(msg =>
                  msg.id === assistantMessageId
                    ? {
                        ...msg,
                        isStreaming: false,
                      }
                    : msg
                ));
              } else if (data.type === 'error') {
                throw new Error(data.error);
              }
            } catch (e) {
              if (line.trim()) {
                console.debug('Skipping unparseable line:', line);
              }
            }
          }
        }
      }

      toast.success('Response completed!');
    } catch (error) {
      console.error('Streaming error details:', error);

      setMessages(prev => prev.map(msg =>
        msg.id === assistantMessageId
          ? {
              ...msg,
              content: 'Sorry, I encountered an error. Please try again.',
              isStreaming: false,
            }
          : msg
      ));

      toast.error('Failed to get response. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleQuestionClick = (question: string) => {
    handleSendMessage(question);
  };

  const handleNewChat = () => {
    setMessages([]);
    toast.success('Started new chat');
  };

  const handleRegenerateResponse = () => {
    toast('Regenerate feature coming soon!', {
      icon: '🔄',
    });
  };

  const handleFeedback = (messageId: string, feedback: 'up' | 'down') => {
    console.log(`Feedback ${feedback} for message ${messageId}`);
  };

  const handleSourceClick = async (source: Source) => {
    console.log('Source clicked:', source);

    try {
      const isVideo = source.content_type === 'video' ||
                     source.content_type === 'lesson_video' ||
                     (source.start_time !== undefined && source.start_time !== null);

      let documentUrl = source.fileUrl;

      if (!documentUrl) {
        try {
          console.log('Trying download endpoint...');
          const urlResponse = await fetch(`${config.API_BASE_URL}/api/ingestion/documents/${encodeURIComponent(source.filename)}/download`);
          if (urlResponse.ok) {
            const urlData = await urlResponse.json();
            documentUrl = urlData.url;
          }
        } catch (error) {
          console.error('Error getting URL from download endpoint:', error);
        }
      }

      if (!documentUrl) {
        try {
          console.log('Trying documents list endpoint...');
          const docsResponse = await fetch(`${config.API_BASE_URL}/api/ingestion/documents?limit=100`);
          const docsData = await docsResponse.json();
          const doc = docsData.documents.find((d: any) => d.filename === source.filename);
          if (doc && doc.fileUrl) {
            documentUrl = doc.fileUrl;
          }
        } catch (error) {
          console.error('Error fetching documents list:', error);
        }
      }

      if (!documentUrl) {
        documentUrl = `${config.API_BASE_URL}/api/documents/${encodeURIComponent(source.filename)}`;
      }

      setSelectedDocument({
        ...source,
        fileUrl: documentUrl
      });

      toast(`Opening ${source.title}...`, {
        icon: isVideo ? '🎥' : '📄',
        duration: 1000,
      });
    } catch (error) {
      console.error('Error in handleSourceClick:', error);
      toast.error('Failed to open source');
    }
  };

  const handleCloseDocument = () => {
    setSelectedDocument(null);
  };

  return (
    <Box
      sx={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        backgroundColor: theme.palette.background.default,
        overflow: 'hidden',
      }}
    >
      {/* Chat Header */}
      <ChatHeader
        conversationTitle={messages.length > 0 ? 'Active Conversation' : 'New Conversation'}
        onNewChat={handleNewChat}
      />

      {/* Messages Area */}
      <Box
        ref={chatContainerRef}
        sx={{
          flex: 1,
          overflowY: 'auto',
          backgroundColor: theme.palette.background.default,
          backgroundImage: `
            radial-gradient(circle at 20% 50%, rgba(0, 134, 214, 0.03) 0%, transparent 50%),
            radial-gradient(circle at 80% 80%, rgba(25, 169, 255, 0.03) 0%, transparent 50%),
            radial-gradient(circle at 40% 20%, rgba(0, 136, 132, 0.02) 0%, transparent 50%)
          `,
        }}
      >
        <Container maxWidth="lg" sx={{ py: 2 }}>
          {messages.length === 0 ? (
            <Box>
              {/* Welcome Message */}
              <Box sx={{ textAlign: 'center', py: 6 }}>
                <Box
                  component="h1"
                  sx={{
                    fontSize: '2.5rem',
                    fontWeight: 700,
                    background: 'linear-gradient(135deg, #071D49 0%, #0086D6 50%, #19A9FF 100%)',
                    WebkitBackgroundClip: 'text',
                    WebkitTextFillColor: 'transparent',
                    mb: 3,
                  }}
                >
                  Welcome to RBL AI
                </Box>
                <Box
                  component="p"
                  sx={{
                    fontSize: '1.125rem',
                    color: 'text.secondary',
                    maxWidth: 700,
                    mx: 'auto',
                    lineHeight: 1.6,
                  }}
                >
                  Powered by Dave Ulrich's decades of research and The RBL Group's expertise.
                  Ask questions about HR, leadership, talent, and organization capability
                </Box>
              </Box>

              {/* Suggested Questions */}
              <SuggestedQuestions
                onQuestionClick={handleQuestionClick}
                visible={true}
              />
            </Box>
          ) : (
            <Stack spacing={2}>
              {messages.map((message) => (
                <MessageBubble
                  key={message.id}
                  message={message}
                  onRegenerateRequest={message.role === 'assistant' ? handleRegenerateResponse : undefined}
                  onFeedback={message.role === 'assistant' ? handleFeedback : undefined}
                  onSourceClick={handleSourceClick}
                />
              ))}
              <div ref={messagesEndRef} />
            </Stack>
          )}
        </Container>
      </Box>

      {/* Input Area */}
      <Box
        sx={{
          borderTop: '1px solid',
          borderColor: 'divider',
          backgroundColor: theme.palette.background.paper,
          p: 2,
          background: `linear-gradient(to top, ${theme.palette.background.paper} 0%, rgba(255,255,255,0.98) 100%)`,
          backdropFilter: 'blur(10px)',
          boxShadow: '0 -4px 20px rgba(0,0,0,0.05)',
        }}
      >
        <Container maxWidth="lg">
          <ChatInput
            onSendMessage={handleSendMessage}
            isLoading={isLoading}
            disabled={isLoading}
          />
        </Container>
      </Box>

      {/* Document/Video Viewer Modal Overlay */}
      {selectedDocument && (
        <Box
          sx={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            zIndex: 1300,
            backgroundColor: 'rgba(0, 0, 0, 0.7)',
            backdropFilter: 'blur(4px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            p: 3,
            animation: 'fadeIn 0.2s ease-out',
            '@keyframes fadeIn': {
              from: { opacity: 0 },
              to: { opacity: 1 },
            },
          }}
          onClick={handleCloseDocument}
        >
          <Box
            sx={{
              width: '90%',
              maxWidth: '1200px',
              height: '90vh',
              backgroundColor: theme.palette.background.paper,
              borderRadius: 3,
              boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden',
              animation: 'slideUp 0.3s ease-out',
              '@keyframes slideUp': {
                from: {
                  opacity: 0,
                  transform: 'translateY(20px) scale(0.98)',
                },
                to: {
                  opacity: 1,
                  transform: 'translateY(0) scale(1)',
                },
              },
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {(selectedDocument.content_type === 'video' ||
              selectedDocument.content_type === 'lesson_video' ||
              (selectedDocument.start_time !== undefined && selectedDocument.start_time !== null)) ? (
              <VideoViewer
                filename={selectedDocument.filename}
                title={selectedDocument.title}
                url={selectedDocument.fileUrl}
                startTime={selectedDocument.start_time}
                allowDownload={true}
                onClose={handleCloseDocument}
              />
            ) : (
              <DocumentViewer
                filename={selectedDocument.filename}
                pageNumber={selectedDocument.page_number}
                title={selectedDocument.title}
                url={selectedDocument.fileUrl}
                allowDownload={true}
                onClose={handleCloseDocument}
              />
            )}
          </Box>
        </Box>
      )}
    </Box>
  );
};

export default Chat;
