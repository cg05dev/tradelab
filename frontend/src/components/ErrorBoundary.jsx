import { useState, useEffect } from 'react';

export default function ErrorBoundary({ children }) {
  const [hasError, setHasError] = useState(false);
  const [errorInfo, setErrorInfo] = useState('');

  useEffect(() => {
    const handleError = (event) => {
      console.error('Error caught:', event);
      setHasError(true);
      
      // Try to extract error details
      let errorDetails = '';
      if (event.error) {
        errorDetails = event.error.toString();
        if (event.error.stack) {
          errorDetails += '\n\nStack:\n' + event.error.stack;
        }
      } else if (event.message) {
        errorDetails = event.message;
      } else {
        errorDetails = JSON.stringify(event, Object.getOwnPropertyNames(event), 2);
      }
      
      setErrorInfo(errorDetails);
    };

    window.addEventListener('error', handleError);
    return () => window.removeEventListener('error', handleError);
  }, []);

  if (hasError) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center p-6">
        <div className="bg-gray-900 border border-red-500/50 rounded-lg p-6 max-w-4xl w-full">
          <h2 className="text-red-400 text-xl font-bold mb-4">Application Error</h2>
          <div className="text-xs text-gray-400 bg-black/50 p-4 rounded overflow-auto max-h-96 font-mono whitespace-pre-wrap">
            {errorInfo || 'No error details available'}
          </div>
          <button 
            onClick={() => window.location.reload()}
            className="mt-4 px-4 py-2 bg-red-500/20 text-red-400 border border-red-500/50 rounded hover:bg-red-500/30 transition-colors"
          >
            Reload App
          </button>
        </div>
      </div>
    );
  }

  return children;
}
