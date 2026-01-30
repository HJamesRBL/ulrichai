import React from 'react';
import {
  Box,
  Paper,
  Typography,
  Stack,
  Chip,
  IconButton,
  Tooltip,
} from '@mui/material';
import {
  Description as DocumentIcon,
  VideoLibrary as VideoIcon,
  OpenInNew as OpenIcon,
  ContentCopy as CopyIcon,
} from '@mui/icons-material';
import { motion } from 'framer-motion';
import toast from 'react-hot-toast';

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

interface SourceCardsProps {
  sources: Source[];
  onSourceClick?: (source: Source) => void;
}

const MotionPaper = motion(Paper);

export const SourceCards: React.FC<SourceCardsProps> = ({ sources, onSourceClick }) => {
  // Debug logging
  console.log('SourceCards component - sources prop:', sources);
  console.log('SourceCards - sources length:', sources ? sources.length : 'sources is null/undefined');

  const formatTimestamp = (seconds: number | undefined): string => {
    if (typeof seconds !== 'number') return '';

    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);

    if (hours > 0) {
      return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    } else {
      return `${minutes}:${secs.toString().padStart(2, '0')}`;
    }
  };

  const handleCopyContent = (content: string) => {
    navigator.clipboard.writeText(content);
    toast.success('Source content copied!');
  };

  // Clean up AI-generated intro text from summaries
  const cleanSummary = (text: string): string => {
    if (!text) return '';
    // Only remove complete preamble phrases that end with colon or period
    const patterns = [
      /^Here is a \d+-?\d* sentence summary[^:]*:\s*/i,
      /^Here is a (comprehensive |brief |concise )?summary[^:]*:\s*/i,
      /^Here's a (comprehensive |brief |concise )?summary[^:]*:\s*/i,
      /^Summary:\s*/i,
    ];
    let cleaned = text;
    for (const pattern of patterns) {
      cleaned = cleaned.replace(pattern, '');
    }
    return cleaned.trim();
  };

  if (!sources || sources.length === 0) {
    console.log('SourceCards - returning null because no sources');
    return null;
  }

  return (
    <Box sx={{ mt: 2, mb: 1, overflow: 'visible' }}>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1.5 }}>
        <Typography variant="subtitle2" fontWeight={600} color="text.secondary">
          📚 Relevant Documents
        </Typography>
        <Chip
          label={`${sources.length} document${sources.length > 1 ? 's' : ''} found`}
          size="small"
          variant="outlined"
        />
      </Stack>

      <Box
        sx={{
          display: 'flex',
          gap: 2,
          overflowX: 'auto',
          overflowY: 'visible',
          py: 1,    // Add vertical padding for lift effect
          px: 0.5,  // Add horizontal padding for border space
          my: -1,   // Compensate with negative margin
          mx: -0.5, // Compensate with negative margin
          '&::-webkit-scrollbar': {
            height: 8,
          },
          '&::-webkit-scrollbar-track': {
            backgroundColor: 'action.hover',
            borderRadius: 4,
          },
          '&::-webkit-scrollbar-thumb': {
            backgroundColor: 'action.disabled',
            borderRadius: 4,
            '&:hover': {
              backgroundColor: 'action.selected',
            },
          },
        }}
      >
        {sources.map((source, idx) => {
          // Parse concepts if provided as comma-separated string
          const conceptsList = source.concepts
            ? source.concepts.split(',').map(c => c.trim()).filter(c => c).slice(0, 4)
            : [];

          // Use summary if available, otherwise fall back to content
          // Clean up any AI-generated preamble text
          const rawContent = source.summary || source.content || '';
          const displayContent = cleanSummary(rawContent);

          return (
            <MotionPaper
              key={idx}
              elevation={0}
              whileHover={{ y: -4 }}
              whileTap={{ scale: 0.98 }}
              sx={{
                p: 2.5,
                minWidth: 340,
                maxWidth: 400,
                cursor: onSourceClick ? 'pointer' : 'default',
                border: '2px solid',
                borderColor: 'divider',
                borderRadius: 2,
                backgroundColor: 'background.paper',
                transition: 'all 0.2s',
                '&:hover': {
                  borderColor: 'primary.main',
                  boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
                },
              }}
              onClick={() => onSourceClick && onSourceClick(source)}
            >
              {/* Header */}
              <Stack direction="row" spacing={1.5} alignItems="flex-start" sx={{ mb: 1.5 }}>
                <Box
                  sx={{
                    width: 40,
                    height: 40,
                    borderRadius: 1.5,
                    backgroundColor: '#19A9FF20',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                  }}
                >
                  <DocumentIcon sx={{ fontSize: 22, color: 'primary.dark' }} />
                </Box>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography
                    variant="subtitle1"
                    fontWeight={600}
                    sx={{
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      display: '-webkit-box',
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: 'vertical',
                      lineHeight: 1.3,
                    }}
                  >
                    {source.title}
                  </Typography>
                  {source.file_type && (
                    <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase' }}>
                      {source.file_type}
                    </Typography>
                  )}
                </Box>
                {/* Relevance Score */}
                <Chip
                  label={`${Math.round(source.score * 100)}% match`}
                  size="small"
                  color="primary"
                  sx={{ height: 26, fontSize: '0.8rem', fontWeight: 600 }}
                />
              </Stack>

              {/* Document Summary */}
              <Typography
                variant="body2"
                color="text.secondary"
                sx={{
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  display: '-webkit-box',
                  WebkitLineClamp: 5,  // Show more lines for document summaries
                  WebkitBoxOrient: 'vertical',
                  mb: 1.5,
                  lineHeight: 1.6,
                  fontSize: '0.875rem',
                }}
              >
                {displayContent}
              </Typography>

              {/* Concepts/Keywords Tags */}
              {conceptsList.length > 0 && (
                <Stack direction="row" spacing={0.5} flexWrap="wrap" sx={{ mb: 1.5, gap: 0.5 }}>
                  {conceptsList.map((concept, i) => (
                    <Chip
                      key={i}
                      label={concept}
                      size="small"
                      variant="outlined"
                      sx={{
                        height: 22,
                        fontSize: '0.7rem',
                        backgroundColor: 'action.hover',
                      }}
                    />
                  ))}
                </Stack>
              )}

              {/* Footer Actions */}
              <Stack direction="row" justifyContent="flex-end" alignItems="center">
                <Stack direction="row" spacing={0.5}>
                  <Tooltip title="Copy summary">
                    <IconButton
                      size="small"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleCopyContent(displayContent);
                      }}
                    >
                      <CopyIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  {onSourceClick && (
                    <Tooltip title="Open document">
                      <IconButton size="small">
                        <OpenIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  )}
                </Stack>
              </Stack>
            </MotionPaper>
          );
        })}
      </Box>
    </Box>
  );
};

export default SourceCards;