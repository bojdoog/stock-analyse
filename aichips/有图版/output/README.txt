美国 AI 算力产业链：流程图、公司关系与实物配图版
资料截至：2026-10-18

文件内容
- output/美国AI算力产业链_流程图册_20261018.pdf：35 页完整图册，含 1 页配图导航、9 张流程图、9 页对应照片、4 页公司目录、8 页产业来源索引和 4 页图片来源。
- output/diagrams/*.png：9 张独立高清图，宽度均为 3840 像素。
- output/diagrams/*.svg：9 张矢量图，可任意放大；文字已转为路径以保证跨设备显示。
- output/photo-diagrams/*.png：9 页独立配图，宽度均为 3840 像素，分别对应总图、制造设备、DDR5 内存、HBM、GPU、TPU、定制 ASIC、服务器、云运营。
- output/photos/assets/*：32 张选用的原始照片、产品图片与结构示意；保留原始文件、完整画面和纵横比。
- output/source/reference_data.json：公司角色与 67 项原始来源。
- output/source/photo_sources.json 与 photo_sources.csv：32 张配图的提供方、型号、图像类型、来源网页、原图地址和原始分辨率。
- output/source/photo_manifest.json：35 页配图版及 9 页配图的索引。
- output/source/manifest.json：原 21 页流程图版及原流程图文件索引。
- output/source/base-atlas.pdf：原 21 页流程图版，供重新组合生成配图版。
- output/source/build_atlas.py 与 build_photo_atlas.py：原流程图与配图版生成脚本。

阅读顺序
00 总图 → 01 芯片底座 → 02 DDR5 内存条 → 03 HBM → 04 GPU/显卡 → 05 TPU → 06 其他定制 ASIC → 07 服务器 → 08 云与应用。
蓝/青实线表示器件工序及硬件交付；紫色实线表示算力/模型服务；灰色虚线表示工具、材料、设施或明确标注的技术支持关系。
同一节点内列出的是代表参与者，并不意味着所有公司互相供货、每家公司都参与每个型号，或所有产品可以互换。
配图页紧随对应流程图。实物照片、现场实拍、官方产品图、产品渲染图与结构示意分别标注，点击图片旁的提供方可打开来源。
3840 像素是整张配图页的宽度，不代表每张来源照片都具有该原始分辨率。图册文字和流程线条可放大，照片细节受原始素材分辨率限制。

范围
以美国设计、设备、系统和云公司为主线，同时列出不可忽略的全球制造、存储、材料和装配伙伴。
这是一份主要模块和代表公司的产业结构图，不是全市场公司穷举、收入排名或特定产品的完整物料清单。
历史产品结构例子和未来合作公告均在图中区分；具体参数不可跨代混用。
照片用于辨认器件、设备与现场形态；各卡片不自动组成同一产品、同一代际或同一批次的完整制造记录。
图片版权属于原提供方，来源与署名随图保留；不能将本文件包理解为所有图片均采用开放许可。TPU v4 作者论文的引文与个人/课堂用途许可说明保留在配图导航页。

重新生成（可选）
Python 依赖：reportlab、PyMuPDF、Pillow。
需要另备 Noto Sans SC 的 Regular/Bold 静态 TTF 字体，放在解压根目录 tmp/fonts/NotoSansSC-Regular.ttf 与 tmp/fonts/NotoSansSC-Bold.ttf。
字体官方来源：https://github.com/google/fonts/tree/main/ofl/notosanssc
若使用可变字体，可用 fontTools 实例化为 400 与 650 字重；字体依其 SIL Open Font License 使用。
重新生成本配图版：在解压根目录运行 python3 output/source/build_photo_atlas.py
脚本读取 output/source/base-atlas.pdf、photo_sources.json 与 output/photos/assets，重建 35 页 PDF、9 页配图 PNG 及 tmp/photo-atlas/review 中的审阅图。
如要重新生成原流程图版：运行 python3 output/source/build_atlas.py。该脚本会输出原 21 页图册以及流程图 PNG/SVG；随后运行配图脚本可恢复完整 35 页版本。
