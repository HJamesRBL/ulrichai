import React, { useState, useRef, useEffect } from 'react';
import {
  Box,
  Container,
  Stack,
  Divider,
  useTheme,
  Paper,
} from '@mui/material';
import { MessageBubble } from './MessageBubble';
import { ChatInput } from './ChatInput';
import { SuggestedQuestions } from './SuggestedQuestions';
import { ChatHeader } from './ChatHeader';
import { Loading } from '../common/Loading';
import toast from 'react-hot-toast';
import { config } from '../../config';
import DocumentViewer from '../DocumentViewer';
import VideoViewer from '../VideoViewer';

interface Source {
  title: string;
  filename: string;
  content: string;
  summary?: string;  // Full document summary
  concepts?: string;  // Comma-separated concepts/keywords
  score: number;
  document_id?: string;
  type?: string;
  file_type?: string;
  fileUrl?: string;
  // Legacy fields for backwards compatibility
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
  // Modal overlay enabled
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [activeAgent, setActiveAgent] = useState('general');
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

    // Add user message
    const userMessage: Message = {
      id: `msg-${Date.now()}-user`,
      content: message,
      role: 'user',
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setIsLoading(true);

    // Add assistant message with streaming indicator
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
          agent: activeAgent,
          session_id: `session-${Date.now()}`,
        }),
      });

      console.log('Response status:', response.status, response.statusText);
      console.log('Response headers:', response.headers);

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      // Read the stream
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
        buffer = lines.pop() || ''; // Keep incomplete line in buffer

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              console.log('Parsed SSE data:', data);

              if (data.type === 'sources') {
                sources = data.sources || [];
                console.log('Received initial sources:', sources.length);
              } else if (data.type === 'sources_update') {
                // Update sources when they arrive later
                sources = data.sources || [];
                console.log('Updated sources:', sources.length);
                // Update the message with new sources
                setMessages(prev => prev.map(msg =>
                  msg.id === assistantMessageId
                    ? { ...msg, sources }
                    : msg
                ));
              } else if (data.type === 'content') {
                accumulatedContent += data.content;
                // Update message with accumulated content
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
                // Mark streaming as complete
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
      console.error('Error type:', error instanceof Error ? error.constructor.name : typeof error);
      console.error('Error message:', error instanceof Error ? error.message : String(error));
      console.error('Error stack:', error instanceof Error ? error.stack : 'No stack trace');

      // Update the streaming message with error
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

  const handleFileUpload = (file: File) => {
    toast.success(`File "${file.name}" uploaded successfully!`);
    // TODO: Implement actual file upload logic
  };

  const handleClearChat = () => {
    setMessages([]);
    toast.success('Chat cleared');
  };

  const handleExportChat = () => {
    const chatContent = messages
      .map(msg => `${msg.role === 'user' ? 'You' : 'Assistant'}: ${msg.content}`)
      .join('\n\n');

    const blob = new Blob([chatContent], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `chat-export-${new Date().toISOString()}.txt`;
    a.click();

    toast.success('Chat exported');
  };

  const handleShareChat = () => {
    // TODO: Implement share functionality
    toast('Share feature coming soon!', {
      icon: '🔗',
    });
  };

  const handleSaveChat = () => {
    // TODO: Implement save functionality
    toast('Save feature coming soon!', {
      icon: '💾',
    });
  };

  const handleNewChat = () => {
    setMessages([]);
    toast.success('Started new chat');
  };

  const handleAgentChange = (agent: string) => {
    setActiveAgent(agent);
    toast.success(`Switched to ${agent} agent`);
  };

  const handleRegenerateResponse = () => {
    // TODO: Implement regenerate functionality
    toast('Regenerate feature coming soon!', {
      icon: '🔄',
    });
  };

  const handleFeedback = (messageId: string, feedback: 'up' | 'down') => {
    // TODO: Implement feedback functionality
    console.log(`Feedback ${feedback} for message ${messageId}`);
  };

  const handleSourceClick = async (source: Source) => {
    console.log('Source clicked:', source);
    console.log('Starting handleSourceClick for:', source.filename);

    try {
      // Detect if this is a video source
      const isVideo = source.content_type === 'video' ||
                     source.content_type === 'lesson_video' ||
                     (source.start_time !== undefined && source.start_time !== null);

      console.log('Is video source:', isVideo);
      console.log('Attempting to get', isVideo ? 'video' : 'document', 'URL');

      // Get the document/video URL from multiple sources
      let documentUrl = source.fileUrl;

      if (!documentUrl) {
        // Try to fetch from the download endpoint (let backend determine bucket)
        try {
          console.log('Trying download endpoint...');
          const urlResponse = await fetch(`${config.API_BASE_URL}/api/ingestion/documents/${encodeURIComponent(source.filename)}/download`);
          console.log('Download endpoint response:', urlResponse.status);
          if (urlResponse.ok) {
            const urlData = await urlResponse.json();
            documentUrl = urlData.url;
            console.log('Got URL from download endpoint:', documentUrl);
          }
        } catch (error) {
          console.error('Error getting URL from download endpoint:', error);
        }
      }

      if (!documentUrl) {
        // Fallback - query the documents endpoint to get the fileUrl
        try {
          console.log('Trying documents list endpoint...');
          const docsResponse = await fetch(`${config.API_BASE_URL}/api/ingestion/documents?limit=100`);
          console.log('Documents list response:', docsResponse.status);
          const docsData = await docsResponse.json();
          const doc = docsData.documents.find((d: any) => d.filename === source.filename);
          if (doc && doc.fileUrl) {
            documentUrl = doc.fileUrl;
            console.log('Got URL from documents list:', documentUrl);
          }
        } catch (error) {
          console.error('Error fetching documents list:', error);
        }
      }

      if (!documentUrl) {
        // Final fallback - use direct endpoint (let backend determine bucket)
        documentUrl = `${config.API_BASE_URL}/api/documents/${encodeURIComponent(source.filename)}`;
        console.log('Using direct endpoint:', documentUrl);
      }

      // Set the selected document with the proper URL
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
      console.error('Error stack:', error instanceof Error ? error.stack : 'No stack');
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
        activeAgent={activeAgent}
        messageCount={messages.length}
        onClearChat={handleClearChat}
        onExportChat={handleExportChat}
        onShareChat={handleShareChat}
        onSaveChat={handleSaveChat}
        onNewChat={handleNewChat}
        onAgentChange={handleAgentChange}
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
            onFileUpload={handleFileUpload}
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
            {/* Check if source is a video */}
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