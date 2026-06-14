from qgis.PyQt.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QSlider, QLabel, 
                                 QComboBox, QWidget, QListWidget, QListWidgetItem, QPushButton, QButtonGroup,
                                 QShortcut)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QKeySequence
from qgis.gui import QgsMapCanvas, QgsMapToolPan, QgsMapTool, QgsRubberBand
from qgis.core import QgsProject, QgsWkbTypes, QgsGeometry, QgsFeature, QgsCoordinateTransform, QgsVectorLayerUtils, Qgis
from qgis.utils import iface

# --- カスタムデジタイズツール ---
class SimpleDigitizeTool(QgsMapTool):
    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas
        self.rubber_band = None
        self.temp_rubber_band = None
        self.points = []
        self.geom_type = None

    def activate(self):
        super().activate()
        self.canvas.setCursor(Qt.CursorShape.CrossCursor)

    def deactivate(self):
        self.reset()
        super().deactivate()

    def reset(self):
        """作図中の赤いガイドラインを消去・リセット"""
        if self.rubber_band:
            self.rubber_band.reset()
            self.rubber_band = None
        if self.temp_rubber_band:
            self.temp_rubber_band.reset()
            self.temp_rubber_band = None
        self.points = []

    def get_active_vector_layer(self):
        """QGIS本体で選択されていて、かつ「編集モード」のベクタレイヤを取得"""
        layer = iface.activeLayer()
        if layer and layer.type() == Qgis.LayerType.Vector and layer.isEditable():
            return layer
        return None

    def canvasReleaseEvent(self, e):
        """キャンバスをクリックして指を離した時の処理"""
        layer = self.get_active_vector_layer()
        if not layer:
            return 

        self.geom_type = layer.geometryType()
        pt = self.toMapCoordinates(e.pos())

        if e.button() == Qt.MouseButton.LeftButton:
            # 左クリック：頂点の追加
            if self.geom_type == QgsWkbTypes.PointGeometry:
                # ポイントの場合は1クリックで即時確定
                self.add_feature(layer, [pt])
            else:
                if not self.rubber_band:
                    self.rubber_band = QgsRubberBand(self.canvas, self.geom_type)
                    self.rubber_band.setColor(Qt.GlobalColor.red)
                    self.rubber_band.setWidth(2)
                if not self.temp_rubber_band:
                    self.temp_rubber_band = QgsRubberBand(self.canvas, self.geom_type)
                    self.temp_rubber_band.setColor(Qt.GlobalColor.red)
                    self.temp_rubber_band.setWidth(1)
                    self.temp_rubber_band.setLineStyle(Qt.PenStyle.DashLine)

                self.points.append(pt)
                self.rubber_band.addPoint(pt, True)

        elif e.button() == Qt.MouseButton.RightButton:
            # 右クリック：図形の確定
            if self.geom_type in (QgsWkbTypes.LineGeometry, QgsWkbTypes.PolygonGeometry):
                # ★属性ダイアログが立ち上がる前に赤い作図線を消す
                final_points = list(self.points)
                self.reset() 
                self.add_feature(layer, final_points)

    def canvasMoveEvent(self, e):
        """マウスを動かした時の破線ガイドの描画"""
        if not self.points or not self.temp_rubber_band:
            return
        
        layer = self.get_active_vector_layer()
        if not layer:
            return

        pt = self.toMapCoordinates(e.pos())
        self.temp_rubber_band.reset(self.geom_type)
        
        if self.geom_type == QgsWkbTypes.LineGeometry:
            self.temp_rubber_band.addPoint(self.points[-1], False)
            self.temp_rubber_band.addPoint(pt, True)
        elif self.geom_type == QgsWkbTypes.PolygonGeometry:
            if len(self.points) > 0:
                self.temp_rubber_band.addPoint(self.points[-1], False)
                self.temp_rubber_band.addPoint(pt, False)
                self.temp_rubber_band.addPoint(self.points[0], True)

    def add_feature(self, layer, points):
        """図形を作成し、属性ダイアログを表示して確定する"""
        if not points: return
        
        # ジオメトリの作成
        if self.geom_type == QgsWkbTypes.PointGeometry:
            geom = QgsGeometry.fromPointXY(points[0])
        elif self.geom_type == QgsWkbTypes.LineGeometry:
            if len(points) < 2: return
            geom = QgsGeometry.fromPolylineXY(points)
        elif self.geom_type == QgsWkbTypes.PolygonGeometry:
            if len(points) < 3: return
            geom = QgsGeometry.fromPolygonXY([points])
        else:
            return
            
        # キャンバスとレイヤの座標系(CRS)が異なる場合は変換
        canvas_crs = self.canvas.mapSettings().destinationCrs()
        layer_crs = layer.crs()
        if canvas_crs != layer_crs:
            transform = QgsCoordinateTransform(canvas_crs, layer_crs, QgsProject.instance())
            geom.transform(transform)
            
        # ★レイヤのデフォルト属性値を加味してフィーチャを作成
        feat = QgsVectorLayerUtils.createFeature(layer, geom)
        
        # ★QGIS標準の「属性入力ダイアログ」を呼び出す
        dialog = iface.getFeatureForm(layer, feat)
        
        # モーダルとして表示し、ユーザーが「OK」を押したか判定する
        if dialog.exec():
            # 入力された属性情報が反映されたフィーチャを取得し、レイヤに追加
            updated_feat = dialog.feature()
            layer.addFeature(updated_feat)
            layer.triggerRepaint()
            self.canvas.refresh()
            
        # ★作図完了後にキャンバスへフォーカスを戻す
        self.canvas.setFocus()

# --------------------------------------

class StereoViewerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Stereo Image Viewer Plugin")
        self.resize(1200, 600)
        
        self.layout = QVBoxLayout(self)
        self.main_layout = QHBoxLayout()
        
        # --- 左側のコントロールパネル ---
        self.list_layout = QVBoxLayout()
        
        self.list_layout.addWidget(QLabel("Left Screen Controls / 左画面操作"))
        self.btn_pan = QPushButton("✋ Pan / 画面移動")
        self.btn_pan.setCheckable(True)
        self.btn_pan.setChecked(True)
        
        self.btn_digitize = QPushButton("✏️ Digitize / デジタイズ")
        self.btn_digitize.setCheckable(True)
        
        self.tool_group = QButtonGroup(self)
        self.tool_group.addButton(self.btn_pan)
        self.tool_group.addButton(self.btn_digitize)
        
        self.list_layout.addWidget(self.btn_pan)
        self.list_layout.addWidget(self.btn_digitize)
        
        msg_label = QLabel("* To use the digitize feature, turn on\nthe edit mode (pencil icon) for the target layer\nin main window. / 作図機能を使うには、\n作図したいレイヤの編集モード（鉛筆マーク）\nをONにしてください。")
        msg_label.setStyleSheet("color: gray; font-size: 11px;")
        self.list_layout.addWidget(msg_label)
        self.list_layout.addSpacing(15)
        
        self.update_btn = QPushButton("🔄 Refresh Layer List /\n レイヤリストを更新")
        self.list_layout.addWidget(self.update_btn)
        
        self.layer_list_widget = QListWidget()
        self.list_layout.addWidget(self.layer_list_widget)
        
        self.list_container = QWidget()
        self.list_container.setLayout(self.list_layout)
        self.list_container.setFixedWidth(250)
        self.main_layout.addWidget(self.list_container)
        
        # マップキャンバスエリア
        self.canvas_layout = QHBoxLayout()
        self.left_canvas = QgsMapCanvas(self)
        self.right_canvas = QgsMapCanvas(self)
        self.left_canvas.setCanvasColor(Qt.GlobalColor.white)
        self.right_canvas.setCanvasColor(Qt.GlobalColor.white)

        self.canvas_layout.addWidget(self.left_canvas)
        self.canvas_layout.addWidget(self.right_canvas)
        
        self.main_layout.addLayout(self.canvas_layout)
        self.layout.addLayout(self.main_layout)
        
        # 下部：コントロールエリア
        self.control_layout = QHBoxLayout()
        
        # 先に視差調整（Parallax Adjustment）を配置
        self.control_layout.addWidget(QLabel("Parallax Adjustment / 視差調整:"))
        self.offset_slider = QSlider(Qt.Orientation.Horizontal)
        self.offset_slider.setMinimum(-5000)
        self.offset_slider.setMaximum(5000)
        self.offset_slider.setValue(0)
        self.offset_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.offset_slider.setMinimumWidth(200)
        self.control_layout.addWidget(self.offset_slider)
        
        self.control_layout.addSpacing(20)
        
        # ★ スライダーとプルダウンの間にズームボタンを配置
        self.btn_zoom_in = QPushButton("➕ Zoom In (F2)")
        self.btn_zoom_out = QPushButton("➖ Zoom Out (F3)")
        self.control_layout.addWidget(self.btn_zoom_in)
        self.control_layout.addWidget(self.btn_zoom_out)
        
        self.control_layout.addSpacing(20)
        
        # 後に右画像選択（Select Right Image）を配置
        self.control_layout.addWidget(QLabel("Select Right Image / 右画像を選択:"))
        self.right_layer_cb = QComboBox()
        self.control_layout.addWidget(self.right_layer_cb)
        
        # 右側に余白を作り、各要素が不自然に広がりすぎないようにする
        self.control_layout.addStretch() 
        
        self.layout.addLayout(self.control_layout)
        
        # 初期化処理
        self.syncing = False
        self.slider_value = 0.0
        self.base_width = 1000.0
        self.populate_layers(preserve_state=False)
        self.setup_canvases()
        
        # シグナルの接続
        self.left_canvas.extentsChanged.connect(self.sync_right_canvas)
        self.right_canvas.extentsChanged.connect(self.sync_left_canvas)
        self.offset_slider.valueChanged.connect(self.update_offset)
        self.right_layer_cb.currentIndexChanged.connect(self.update_canvas_layers)
        self.layer_list_widget.itemChanged.connect(self.update_canvas_layers)
        self.update_btn.clicked.connect(self.refresh_layers)
        
        QgsProject.instance().layersAdded.connect(self.refresh_layers)
        QgsProject.instance().layersRemoved.connect(self.refresh_layers)
        
        self.btn_pan.clicked.connect(self.set_pan_tool)
        self.btn_digitize.clicked.connect(self.set_digitize_tool)
        
        # ズームボタンとショートカットキーの接続
        self.btn_zoom_in.clicked.connect(self.zoom_in)
        self.btn_zoom_out.clicked.connect(self.zoom_out)
        
        self.shortcut_zoom_in = QShortcut(QKeySequence("F2"), self)
        self.shortcut_zoom_in.activated.connect(self.zoom_in)
        
        self.shortcut_zoom_out = QShortcut(QKeySequence("F3"), self)
        self.shortcut_zoom_out.activated.connect(self.zoom_out)

    def zoom_in(self):
        self.left_canvas.zoomIn()

    def zoom_out(self):
        self.left_canvas.zoomOut()

    def set_pan_tool(self):
        self.left_canvas.setMapTool(self.pan_tool_left)
        self.left_canvas.setFocus()

    def set_digitize_tool(self):
        self.left_canvas.setMapTool(self.digitize_tool)
        self.left_canvas.setFocus()

    def populate_layers(self, preserve_state=False):
        checked_layers = []
        current_right_id = None
        if preserve_state:
            for i in range(self.layer_list_widget.count()):
                item = self.layer_list_widget.item(i)
                if item.checkState() == Qt.CheckState.Checked:
                    checked_layers.append(item.data(Qt.ItemDataRole.UserRole))
            current_right_id = self.right_layer_cb.currentData()

        self.layer_list_widget.blockSignals(True)
        self.right_layer_cb.blockSignals(True)
        self.layer_list_widget.clear()
        self.right_layer_cb.clear()
        
        root = QgsProject.instance().layerTreeRoot()
        for tree_layer in root.findLayers():
            layer = tree_layer.layer()
            if layer:
                item = QListWidgetItem(layer.name())
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                if preserve_state:
                    if layer.id() in checked_layers:
                        item.setCheckState(Qt.CheckState.Checked)
                    else:
                        item.setCheckState(Qt.CheckState.Unchecked)
                else:
                    if tree_layer.isVisible():
                        item.setCheckState(Qt.CheckState.Checked)
                    else:
                        item.setCheckState(Qt.CheckState.Unchecked)
                        
                item.setData(Qt.ItemDataRole.UserRole, layer.id())
                self.layer_list_widget.addItem(item)
                self.right_layer_cb.addItem(layer.name(), layer.id())

        if preserve_state and current_right_id:
            idx = self.right_layer_cb.findData(current_right_id)
            if idx >= 0:
                self.right_layer_cb.setCurrentIndex(idx)
        elif self.right_layer_cb.count() > 1:
            self.right_layer_cb.setCurrentIndex(1)

        self.layer_list_widget.blockSignals(False)
        self.right_layer_cb.blockSignals(False)
        if preserve_state:
            self.update_canvas_layers()

    def refresh_layers(self, *args):
        self.populate_layers(preserve_state=True)

    def setup_canvases(self):
        crs = QgsProject.instance().crs()
        self.left_canvas.setDestinationCrs(crs)
        self.right_canvas.setDestinationCrs(crs)
        
        self.pan_tool_left = QgsMapToolPan(self.left_canvas)
        self.pan_tool_right = QgsMapToolPan(self.right_canvas)
        self.digitize_tool = SimpleDigitizeTool(self.left_canvas)
        
        self.left_canvas.setMapTool(self.pan_tool_left)
        self.right_canvas.setMapTool(self.pan_tool_right)

        if iface is not None and iface.mapCanvas() is not None:
            self.left_canvas.setExtent(iface.mapCanvas().extent())
        
        self.base_width = self.left_canvas.extent().width()
        if self.base_width == 0:
            self.base_width = 1000.0
            
        self.update_canvas_layers()

    def update_canvas_layers(self, *args):
        left_display_layers = []
        for i in range(self.layer_list_widget.count()):
            item = self.layer_list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                layer_id = item.data(Qt.ItemDataRole.UserRole)
                layer = QgsProject.instance().mapLayer(layer_id)
                if layer:
                    left_display_layers.append(layer)
        
        right_layer_id = self.right_layer_cb.currentData()
        right_layer = QgsProject.instance().mapLayer(right_layer_id)
        right_display_layers = [right_layer] if right_layer else []

        self.left_canvas.setLayers(left_display_layers)
        self.right_canvas.setLayers(right_display_layers)
        self.left_canvas.refresh()
        self.right_canvas.refresh()

    def update_offset(self, value):
        self.slider_value = value
        self.sync_right_canvas()

    def sync_right_canvas(self):
        if self.syncing: return
        self.syncing = True
        
        left_ext = self.left_canvas.extent()
        
        # ★拡大時により大きく距離を離すための計算
        current_width = left_ext.width()
        blended_width = (current_width * 1.0) + (self.base_width * 0.0)
        scale_factor = blended_width / 4000.0
        
        current_offset = self.slider_value * scale_factor
        
        left_ext.setXMinimum(left_ext.xMinimum() + current_offset)
        left_ext.setXMaximum(left_ext.xMaximum() + current_offset)
        
        self.right_canvas.setExtent(left_ext)
        self.right_canvas.refresh()
        self.syncing = False

    def sync_left_canvas(self):
        if self.syncing: return
        self.syncing = True
        
        right_ext = self.right_canvas.extent()
        
        # ★拡大時により大きく距離を離すための計算
        current_width = right_ext.width()
        blended_width = (current_width * 1.0) + (self.base_width * 0.0)
        scale_factor = blended_width / 4000.0
        
        current_offset = self.slider_value * scale_factor
        
        right_ext.setXMinimum(right_ext.xMinimum() - current_offset)
        right_ext.setXMaximum(right_ext.xMaximum() - current_offset)
        
        self.left_canvas.setExtent(right_ext)
        self.left_canvas.refresh()
        self.syncing = False

    def closeEvent(self, event):
        try:
            QgsProject.instance().layersAdded.disconnect(self.refresh_layers)
            QgsProject.instance().layersRemoved.disconnect(self.refresh_layers)
        except:
            pass
        super().closeEvent(event)

# --- QGISプラグインとしての登録部分 ---
class StereoViewerPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.viewer = None
        self.action = None

    def initGui(self):
        import os
        from qgis.PyQt.QtWidgets import QAction
        from qgis.PyQt.QtGui import QIcon

        icon_path = os.path.join(os.path.dirname(__file__), 'icon.png')
        self.action = QAction(QIcon(icon_path), "Launch Stereo Viewer", self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&Stereo Image Viewer Plugin", self.action)

    def unload(self):
        self.iface.removePluginMenu("&Stereo Image Viewer Plugin", self.action)
        self.iface.removeToolBarIcon(self.action)
        if self.viewer:
            self.viewer.close()

    def run(self):
        if not self.viewer or self.viewer.isHidden():
            self.viewer = StereoViewerDialog(self.iface.mainWindow())
        self.viewer.show()