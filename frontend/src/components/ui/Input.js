// components/ui/Input.js
export const Input = ({ type = "text", value, onChange, min, max, className = "" }) => {
    return (
      <input
        type={type}
        value={value}
        onChange={onChange}
        min={min}
        max={max}
        className={`w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 ${className}`}
      />
    );
  };