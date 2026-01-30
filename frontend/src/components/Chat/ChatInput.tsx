import React, { useState, KeyboardEvent } from 'react';
import {
  Box,
  TextField,
  IconButton,
  Paper,
  Stack,
  CircularProgress,
  Typography,
} from '@mui/material';
import {
  Send as SendIcon,
} from '@mui/icons-material';
import { motion } from 'framer-motion';

interface ChatInputProps {
  onSendMessage: (message: string) => void;
  isLoading?: boolean;
  disabled?: boolean;
  placeholder?: string;
}

const MotionBox = motion(Box);

export const ChatInput: React.FC<ChatInputProps> = ({
  onSendMessage,
  isLoading = false,
  disabled = false,
  placeholder = "Ask anything...",
}) => {
  const [message, setMessage] = useState('');

  const handleSend = () => {
    if (message.trim() && !isLoading && !disabled) {
      onSendMessage(message);
      setMessage('');
    }
  };

  const handleKeyPress = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleMessageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setMessage(e.target.value);
  };

  return (
    <Box sx={{ position: 'relative' }}>
      <Paper
        elevation={0}
        sx={{
          p: 2.5,
          borderRadius: 3,
          backgroundColor: 'background.paper',
          border: '2px solid',
          borderColor: 'divider',
          transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
          '&:focus-within': {
            borderColor: 'primary.main',
            boxShadow: '0 8px 24px rgba(0, 134, 214, 0.15)',
          },
        }}
      >
        <Stack spacing={2}>
          {/* Main Input Area */}
          <Stack direction="row" spacing={1} alignItems="flex-end">
            {/* Text Input */}
            <TextField
              fullWidth
              multiline
              maxRows={4}
              value={message}
              onChange={handleMessageChange}
              onKeyPress={handleKeyPress}
              placeholder={placeholder}
              disabled={disabled || isLoading}
              variant="standard"
              InputProps={{
                disableUnderline: true,
                sx: {
                  fontSize: '0.95rem',
                  px: 1,
                },
              }}
              sx={{
                '& .MuiInput-root': {
                  backgroundColor: 'action.hover',
                  borderRadius: 2,
                  px: 1.5,
                  py: 1,
                  transition: 'background-color 0.2s',
                  '&:hover': {
                    backgroundColor: 'action.selected',
                  },
                  '&.Mui-focused': {
                    backgroundColor: 'action.selected',
                  },
                },
              }}
            />

            {/* Send Button */}
            <MotionBox
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              <IconButton
                onClick={handleSend}
                disabled={!message.trim() || isLoading || disabled}
                sx={{
                  background: 'linear-gradient(135deg, #0086D6 0%, #19A9FF 100%)',
                  color: 'white',
                  width: 44,
                  height: 44,
                  boxShadow: '0 4px 14px rgba(0, 134, 214, 0.3)',
                  transition: 'all 0.3s',
                  '&:hover': {
                    background: 'linear-gradient(135deg, #071D49 0%, #0086D6 100%)',
                    boxShadow: '0 8px 20px rgba(0, 134, 214, 0.4)',
                  },
                  '&.Mui-disabled': {
                    backgroundColor: 'action.disabledBackground',
                    boxShadow: 'none',
                  },
                }}
              >
                {isLoading ? (
                  <CircularProgress size={20} sx={{ color: 'white' }} />
                ) : (
                  <SendIcon sx={{ fontSize: 20 }} />
                )}
              </IconButton>
            </MotionBox>
          </Stack>

          {/* Character Count & Shortcuts */}
          <Stack
            direction="row"
            justifyContent="space-between"
            alignItems="center"
          >
            <Stack direction="row" spacing={2}>
              <Typography variant="caption" color="text.secondary">
                {message.length}/4000
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Press Enter to send • Shift+Enter for new line
              </Typography>
            </Stack>
          </Stack>
        </Stack>
      </Paper>
    </Box>
  );
};

export default ChatInput;
