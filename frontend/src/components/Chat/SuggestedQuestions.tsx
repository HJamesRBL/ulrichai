import React from 'react';
import {
  Box,
  Stack,
  Typography,
  Fade,
  Paper,
} from '@mui/material';
import {
  AutoAwesome as SparkleIcon,
  Business as BusinessIcon,
  Groups as TeamsIcon,
  Psychology as LeadershipIcon,
  TrendingUp as PerformanceIcon,
} from '@mui/icons-material';
import { motion } from 'framer-motion';

interface SuggestedQuestionsProps {
  questions?: string[];
  onQuestionClick: (question: string) => void;
  visible?: boolean;
}

const defaultQuestions = [
  {
    icon: <LeadershipIcon />,
    text: "What are the key dimensions of effective leadership?",
    category: "leadership",
  },
  {
    icon: <BusinessIcon />,
    text: "How can HR create more value for the business?",
    category: "hr",
  },
  {
    icon: <TeamsIcon />,
    text: "What builds high-performing organizational cultures?",
    category: "culture",
  },
  {
    icon: <PerformanceIcon />,
    text: "How do we measure organizational capability?",
    category: "performance",
  },
];

export const SuggestedQuestions: React.FC<SuggestedQuestionsProps> = ({
  questions,
  onQuestionClick,
  visible = true,
}) => {
  const displayQuestions = questions || defaultQuestions.map(q => q.text);

  const containerVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: {
      opacity: 1,
      y: 0,
      transition: {
        staggerChildren: 0.1,
      },
    },
  };

  const itemVariants = {
    hidden: { opacity: 0, scale: 0.8 },
    visible: {
      opacity: 1,
      scale: 1,
      transition: {
        type: 'spring',
        stiffness: 100,
      },
    },
  };

  if (!visible) return null;

  return (
    <Fade in={visible} timeout={500}>
      <Box sx={{ px: 2, py: 3 }}>
        {/* Header with Gradient */}
        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 3, px: 1 }}>
          <Box
            sx={{
              background: 'linear-gradient(135deg, #071D49 0%, #0086D6 100%)',
              borderRadius: '8px',
              p: 0.5,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <SparkleIcon sx={{ color: 'white', fontSize: 18 }} />
          </Box>
          <Typography
            variant="h6"
            sx={{
              fontWeight: 700,
              background: 'linear-gradient(135deg, #071D49 0%, #0086D6 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
            }}
          >
            Suggested Questions
          </Typography>
        </Stack>

        {/* Questions Grid */}
        <motion.div
          variants={containerVariants}
          initial="hidden"
          animate="visible"
        >
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' },
              gap: 2,
            }}
          >
            {displayQuestions.map((question, index) => {
              const defaultQ = defaultQuestions[index];
              const icon = defaultQ?.icon || <SparkleIcon />;
              const category = defaultQ?.category || 'general';

              // Define gradient colors for each category
              const gradients = {
                leadership: 'linear-gradient(135deg, #071D49 0%, #0086D6 100%)',
                hr: 'linear-gradient(135deg, #0086D6 0%, #19A9FF 100%)',
                culture: 'linear-gradient(135deg, #008884 0%, #5EC4B6 100%)',
                performance: 'linear-gradient(135deg, #E8B70B 0%, #F0C83B 100%)',
                general: 'linear-gradient(135deg, #071D49 0%, #0086D6 100%)',
              };

              return (
                <motion.div key={index} variants={itemVariants} style={{ height: '100%' }}>
                  <Paper
                    onClick={() => onQuestionClick(question)}
                    elevation={0}
                    sx={{
                      p: 3,
                      height: '100%',
                      cursor: 'pointer',
                      position: 'relative',
                      overflow: 'hidden',
                      background: 'background.paper',
                      border: '2px solid transparent',
                      borderRadius: 3,
                      transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
                      '&::before': {
                        content: '""',
                        position: 'absolute',
                        top: 0,
                        left: 0,
                        right: 0,
                        bottom: 0,
                        borderRadius: 3,
                        padding: '2px',
                        background: gradients[category as keyof typeof gradients],
                        WebkitMask: 'linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)',
                        WebkitMaskComposite: 'xor',
                        maskComposite: 'exclude',
                        opacity: 0,
                        transition: 'opacity 0.3s',
                      },
                      '&:hover': {
                        transform: 'translateY(-4px)',
                        boxShadow: '0 12px 40px rgba(0, 134, 214, 0.15)',
                        '&::before': {
                          opacity: 1,
                        },
                        '& .icon-container': {
                          transform: 'scale(1.1) rotate(5deg)',
                        },
                      },
                      '&:active': {
                        transform: 'translateY(-2px)',
                      },
                    }}
                  >
                    {/* Gradient Overlay on Hover */}
                    <Box
                      sx={{
                        position: 'absolute',
                        top: 0,
                        left: 0,
                        right: 0,
                        bottom: 0,
                        background: gradients[category as keyof typeof gradients],
                        opacity: 0,
                        transition: 'opacity 0.3s',
                        borderRadius: 3,
                        '&:hover': {
                          opacity: 0.03,
                        },
                      }}
                    />

                    <Stack spacing={2} sx={{ position: 'relative', zIndex: 1 }}>
                      {/* Icon */}
                      <Box
                        className="icon-container"
                        sx={{
                          width: 40,
                          height: 40,
                          borderRadius: '10px',
                          background: gradients[category as keyof typeof gradients],
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          color: 'white',
                          transition: 'transform 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
                          boxShadow: '0 4px 14px rgba(0, 134, 214, 0.25)',
                        }}
                      >
                        {icon}
                      </Box>

                      {/* Question Text */}
                      <Typography
                        variant="body1"
                        sx={{
                          fontWeight: 500,
                          lineHeight: 1.5,
                          color: 'text.primary',
                        }}
                      >
                        {question}
                      </Typography>

                      {/* Hover Indicator */}
                      <Box
                        sx={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 0.5,
                          color: 'primary.main',
                          fontSize: '0.875rem',
                          fontWeight: 600,
                          opacity: 0,
                          transform: 'translateX(-10px)',
                          transition: 'all 0.3s',
                          'div:hover &': {
                            opacity: 1,
                            transform: 'translateX(0)',
                          },
                        }}
                      >
                        Ask this question →
                      </Box>
                    </Stack>
                  </Paper>
                </motion.div>
              );
            })}
          </Box>
        </motion.div>
      </Box>
    </Fade>
  );
};

export default SuggestedQuestions;
