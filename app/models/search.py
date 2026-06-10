"""搜索记录 & 搜索结果模型"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class SearchRecord(Base):
    __tablename__ = 'search_records'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'),
                     nullable=False, index=True)
    keyword = Column(String(200), nullable=False)
    source = Column(String(20), nullable=False, default='manual')  # manual / scheduled
    status = Column(String(20), default='completed')  # completed / failed / processing
    total_found = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    # 关联
    user = relationship('User', back_populates='searches')
    result_items = relationship('SearchResultItem', back_populates='search_record',
                                cascade='all, delete-orphan', lazy='selectin',
                                order_by='SearchResultItem.rank')
    analysis_reports = relationship('AnalysisReport', back_populates='search_record',
                                    cascade='all, delete-orphan', lazy='dynamic')

    def __repr__(self):
        return f'<SearchRecord "{self.keyword}" by user_{self.user_id}>'


class SearchResultItem(Base):
    __tablename__ = 'search_result_items'

    id = Column(Integer, primary_key=True, autoincrement=True)
    search_id = Column(Integer, ForeignKey('search_records.id', ondelete='CASCADE'),
                       nullable=False, index=True)
    rank = Column(Integer, nullable=False)
    title = Column(String(500), nullable=False)
    source_name = Column(String(200), nullable=False)
    source_url = Column(String(1000), nullable=True)
    published_at = Column(DateTime, nullable=True)
    summary = Column(Text, nullable=True)
    authority_score = Column(Float, default=0.0)
    recency_score = Column(Float, default=0.0)
    relevance_score = Column(Float, default=0.0)
    engagement_score = Column(Float, default=0.0)
    total_score = Column(Float, nullable=False, index=True)
    selected_for_analysis = Column(Boolean, default=False)

    # 关联
    search_record = relationship('SearchRecord', back_populates='result_items')

    def __repr__(self):
        return f'<SearchResultItem #{self.rank} "{self.title[:30]}...">'


class AnalysisReport(Base):
    __tablename__ = 'analysis_reports'

    id = Column(Integer, primary_key=True, autoincrement=True)
    search_id = Column(Integer, ForeignKey('search_records.id', ondelete='CASCADE'),
                       nullable=False)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'),
                     nullable=False, index=True)
    analyzed_items = Column(Text, nullable=True)  # JSON: 被分析的新闻ID列表
    report_content = Column(Text, nullable=False)
    generated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # 关联
    search_record = relationship('SearchRecord', back_populates='analysis_reports')
    user = relationship('User', back_populates='analysis_reports')

    def __repr__(self):
        return f'<AnalysisReport for search_{self.search_id}>'
