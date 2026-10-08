import { useState, useCallback } from 'react';

export default function UserUpload({ handleName, onUploadFinished }) {
  const [file, setFile] = useState(null);
  const [address, setAddress] = useState('');
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState('');

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    const dropped = Array.from(e.dataTransfer.files)[0];
    setFile(dropped);
  }, []);

  const handleDragOver = (e) => {
    e.preventDefault();
  };

  const handleFileChange = (e) => {
    const selected = e.target.files[0];
    setFile(selected);
  };

  const handleSubmit = async () => {
    if (!file) {
      setMessage('Please provide both file and address.');
      return;
    }
    setUploading(true);
    setMessage('');
    try {
      const formData = new FormData();
      formData.append('file', file);

      const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
      const res = await fetch(`${apiBase}/upload`, {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) throw new Error('Upload failed');

      const data = await res.json();
      
      handleName(data.blob_name);
      setMessage(`Upload successful! Processing started...`);
      
      // flagged time to fetch
      onUploadFinished();

    } catch (err) {
      setMessage(err.message);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="max-w-md mx-auto p-4 space-y-4 border rounded-lg shadow-sm">
      <h2 className="text-xl font-semibold">Upload File & Location</h2>

      <div
        className="flex flex-col items-center justify-center p-6 border-2 border-dashed rounded cursor-pointer hover:bg-gray-50"
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onClick={() => document.getElementById('fileInput').click()}
      >
        {file
          ? <p>{file.name}</p>
          : <p>Drag & drop file here, or click to select<br/>(jpeg, jpg, png, pdf, mp4)</p>
        }
        <input
          id="fileInput"
          type="file"
          accept="image/jpeg,image/jpg,image/png,application/pdf,video/mp4"
          className="hidden"
          onChange={handleFileChange}
        />
      </div>

      <input
        type="text"
        placeholder="Enter address"
        value={address}
        onChange={(e) => setAddress(e.target.value)}
        className="w-full p-2 border rounded focus:outline-none focus:ring"
      />

      <button
        onClick={handleSubmit}
        disabled={uploading}
        className="w-full py-2 font-medium text-white bg-blue-600 rounded hover:bg-blue-700 disabled:opacity-50"
      >
        {uploading ? 'Uploading...' : 'Submit'}
      </button>

      {message && <p className="text-center text-sm text-gray-600">{message}</p>}
    </div>
  );
}
