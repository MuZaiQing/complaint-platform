package org.example;

import org.apache.commons.csv.CSVFormat;
import org.apache.commons.csv.CSVParser;
import org.apache.commons.csv.CSVRecord;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.io.LongWritable;
import org.apache.hadoop.io.Text;
import org.apache.hadoop.mapreduce.Job;
import org.apache.hadoop.mapreduce.Mapper;
import org.apache.hadoop.mapreduce.Reducer;
import org.apache.hadoop.mapreduce.lib.input.FileInputFormat;
import org.apache.hadoop.mapreduce.lib.output.FileOutputFormat;

import java.io.IOException;
import java.io.StringReader;

public class ProductTimelyCount {

    public static class ProductTimelyMapper
            extends Mapper<LongWritable, Text, Text, LongWritable> {

        private final Text outKey = new Text();
        private final LongWritable outValue = new LongWritable(1);

        @Override
        protected void map(LongWritable key, Text value, Context context)
                throws IOException, InterruptedException {
            String line = value.toString();

            // 跳过表头
            if (line.startsWith("Date received,")) {
                return;
            }

            try (CSVParser parser = CSVParser.parse(new StringReader(line), CSVFormat.DEFAULT)) {
                for (CSVRecord record : parser) {
                    // 确保字段数足够：Product(1) + Timely response?(13)
                    if (record.size() < 14) {
                        context.getCounter("ProductTimely", "INVALID_CSV").increment(1);
                        return;
                    }

                    String product = record.get(1).trim();
                    String timelyFlag = record.get(13).trim();

                    // 空值跳过
                    if (product.isEmpty() || timelyFlag.isEmpty()) {
                        context.getCounter("ProductTimely", "EMPTY_FIELD").increment(1);
                        return;
                    }

                    // 复合key：产品名,回复状态 （逗号分隔）
                    String compositeKey = product + "," + timelyFlag;
                    outKey.set(compositeKey);
                    context.write(outKey, outValue);
                }
            } catch (Exception e) {
                context.getCounter("ProductTimely", "PARSE_ERROR").increment(1);
            }
        }
    }

    public static class ProductTimelyReducer
            extends Reducer<Text, LongWritable, Text, LongWritable> {
        private final LongWritable result = new LongWritable();
        @Override
        protected void reduce(Text key, Iterable<LongWritable> values, Context context)
                throws IOException, InterruptedException {
            long sum = 0;
            for (LongWritable v : values) sum += v.get();
            result.set(sum);
            context.write(key, result);
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("用法：ProductTimelyCount <输入路径> <输出路径>");
            System.exit(2);
        }
        Configuration conf = new Configuration();
        Job job = Job.getInstance(conf, "CFPB Product Timely Response Count");
        job.setJarByClass(ProductTimelyCount.class);

        job.setMapperClass(ProductTimelyMapper.class);
        job.setCombinerClass(ProductTimelyReducer.class);
        job.setReducerClass(ProductTimelyReducer.class);

        job.setMapOutputKeyClass(Text.class);
        job.setMapOutputValueClass(LongWritable.class);
        job.setOutputKeyClass(Text.class);
        job.setOutputValueClass(LongWritable.class);
        job.setNumReduceTasks(1);

        FileInputFormat.addInputPath(job, new Path(args[0]));
        FileOutputFormat.setOutputPath(job, new Path(args[1]));
        System.exit(job.waitForCompletion(true) ? 0 : 1);
    }
}
