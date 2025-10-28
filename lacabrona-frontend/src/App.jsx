import * as React from 'react'
import {
  AppBar,
  Box,
  Button,
  Container,
  IconButton,
  Toolbar,
  Typography
} from '@mui/material'
import MenuIcon from '@mui/icons-material/Menu'

export default function App() {
  return (
    <Box sx={{ flexGrow: 1 }}>
      <AppBar position="static">
        <Toolbar>
          <IconButton size="large" edge="start" color="inherit" aria-label="menu" sx={{ mr: 2 }}>
            <MenuIcon />
          </IconButton>
          <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
            Lacabrona Frontend
          </Typography>
          <Button color="inherit" href="http://localhost:8000" target="_blank" rel="noreferrer">
            API 8000
          </Button>
        </Toolbar>
      </AppBar>
      <Container sx={{ py: 6 }}>
        <Typography variant="h4" gutterBottom>
          React + MUI is running
        </Typography>
        <Typography variant="body1" gutterBottom>
          Edit <code>lacabrona-frontend/src/App.jsx</code> and save to reload.
        </Typography>
        <Box sx={{ mt: 4 }}>
          <Button variant="contained">Primary Action</Button>
        </Box>
      </Container>
    </Box>
  )
}

