import matplotlib.pyplot as plt
import seaborn as sns
import json
import argparse

def main(args):
    with open(args.data_file_path, 'r') as json_file:
        target_data = json.load(json_file)

    x_values = []
    y_values = []

    for price, value in target_data:
        x_values.append(value)
        y_values.append(price)

    # 산포도 그리기
    plt.figure(figsize=(15, 9))
    plt.scatter(x_values, y_values, color='blue', marker='o')

    # 제목 및 레이블 설정
    plt.title('Scatter Plot of Data')
    plt.xlabel('Sum of the valid option grade')
    plt.ylabel('Price')

    # 이미지로 저장 (png 형식)
    plt.savefig('scatter_plot_2d.png', dpi=300)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Data Visualization")
    
    # CLI 인자 정의
    parser.add_argument('--data_file_path', type=str, required=True, help="Visualization 할 데이터 파일 경로")

    args = parser.parse_args()
    main(args)