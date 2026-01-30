import React from 'react';
import {
  Box,
  Stack,
  Typography,
  IconButton,
  Tooltip,
} from '@mui/material';
import {
  RestartAlt as RestartIcon,
} from '@mui/icons-material';

interface ChatHeaderProps {
  conversationTitle?: string;
  onNewChat?: () => void;
}

export const ChatHeader: React.FC<ChatHeaderProps> = ({
  conversationTitle = 'New Conversation',
  onNewChat,
}) => {
  return (
    <Box
      sx={{
        px: 3,
        py: 2,
        backgroundColor: 'background.paper',
        borderBottom: '1px solid',
        borderColor: 'divider',
        position: 'sticky',
        top: 0,
        zIndex: 10,
      }}
    >
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        {/* Left Section */}
        <Box>
          <Typography variant="subtitle1" fontWeight={600}>
            {conversationTitle}
          </Typography>
        </Box>

        {/* Right Section */}
        <Stack direction="row" spacing={1}>
          <Tooltip title="New chat">
            <IconButton onClick={onNewChat} size="small">
              <RestartIcon />
            </IconButton>
          </Tooltip>
        </Stack>
      </Stack>
    </Box>
  );
};

export default ChatHeader;
