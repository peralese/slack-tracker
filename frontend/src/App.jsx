import { useState } from 'react';
import { triggerPoll } from './api';
import ItemList from './components/ItemList';
import './App.css';

export default function App() {
  const [polling,  setPolling]  = useState(false);
  const [pollMsg,  setPollMsg]  = useState('');

  async function handleTriggerPoll() {
    setPolling(true);
    setPollMsg('');
    try {
      await triggerPoll();
      setPollMsg('Poll triggered — new messages will appear shortly.');
    } catch {
      setPollMsg('Failed to trigger poll. Is the backend running?');
    } finally {
      setPolling(false);
      setTimeout(() => setPollMsg(''), 5000);
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>Slack Tracker</h1>
        <button
          className="poll-button"
          onClick={handleTriggerPoll}
          disabled={polling}
        >
          {polling ? 'Polling…' : 'Trigger Poll'}
        </button>
      </header>

      {pollMsg && <p className="poll-msg">{pollMsg}</p>}

      <main>
        <ItemList />
      </main>
    </div>
  );
}
