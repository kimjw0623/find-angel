// components/ui/Button.js
export const Button = ({ children, onClick, type = "button", className = "" }) => {
    return (
      <button
        type={type}
        onClick={onClick}
        className={`px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500 ring-offset-2 ${className}`}
      >
        {children}
      </button>
    );
  };